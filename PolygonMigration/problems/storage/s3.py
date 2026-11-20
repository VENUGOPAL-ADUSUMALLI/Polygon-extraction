"""
AWS S3 implementation of TestCaseStorage (boto3).

Configuration (environment variables, read in settings.py):
    AWS_S3_BUCKET_NAME      bucket to write to (required)
    AWS_REGION              bucket region, e.g. ap-south-1 (required)
    AWS_ACCESS_KEY_ID       optional; if unset, boto3's default credential
    AWS_SECRET_ACCESS_KEY   chain is used (IAM role, ~/.aws/credentials, ...)

Required IAM permissions on the bucket:
    s3:PutObject, s3:ListBucket, s3:DeleteObject
"""
import logging

import boto3
from django.core.exceptions import ImproperlyConfigured

from .base import TestCaseStorage, problem_prefix

logger = logging.getLogger(__name__)

# DeleteObjects accepts at most 1000 keys per request.
_DELETE_BATCH_SIZE = 1000


class S3Storage(TestCaseStorage):
    display_name = "AWS S3"

    def __init__(self, bucket_name, region, access_key_id=None, secret_access_key=None, client=None):
        if not bucket_name:
            raise ImproperlyConfigured("AWS_S3_BUCKET_NAME must be set when STORAGE_PROVIDER=s3")
        if not region:
            raise ImproperlyConfigured("AWS_REGION must be set when STORAGE_PROVIDER=s3")
        self.bucket_name = bucket_name
        # `client` can be injected (e.g. a stubbed client in tests).
        self.client = client or boto3.client(
            "s3",
            region_name=region,
            # None -> boto3 falls back to its default credential chain.
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )

    @classmethod
    def from_settings(cls, settings):
        return cls(
            bucket_name=settings.AWS_S3_BUCKET_NAME,
            region=settings.AWS_REGION,
            access_key_id=settings.AWS_ACCESS_KEY_ID,
            secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    def upload_file(self, key, data):
        self.client.put_object(Bucket=self.bucket_name, Key=key, Body=data)
        logger.info("Uploaded s3://%s/%s (%d bytes)", self.bucket_name, key, len(data))

    def delete_problem_files(self, problem_id):
        prefix = problem_prefix(problem_id)
        paginator = self.client.get_paginator("list_objects_v2")
        keys = [
            obj["Key"]
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            for obj in page.get("Contents", [])
        ]

        for start in range(0, len(keys), _DELETE_BATCH_SIZE):
            batch = keys[start:start + _DELETE_BATCH_SIZE]
            response = self.client.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            errors = response.get("Errors", [])
            if errors:
                raise RuntimeError(f"Failed to delete {len(errors)} object(s) under s3://{self.bucket_name}/{prefix}: {errors[:3]}")

        logger.info("Deleted %d object(s) under s3://%s/%s", len(keys), self.bucket_name, prefix)
        return len(keys)
