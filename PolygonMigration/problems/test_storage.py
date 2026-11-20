"""
Unit tests for the pluggable test-case storage (problems/storage/).

S3 calls are intercepted with botocore's Stubber, so no AWS account or network
access is needed. Run with:
    python manage.py test problems.test_storage
"""
import boto3
from botocore.stub import Stubber
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from problems.storage import get_storage
from problems.storage.base import (
    TestCaseStorage,
    problem_file_key,
    problem_prefix,
    test_input_key,
    test_output_key,
)
from problems.storage.s3 import S3Storage

BUCKET = "test-bucket"


def make_s3_storage():
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    return S3Storage(bucket_name=BUCKET, region="us-east-1", client=client), Stubber(client)


class KeyLayoutTests(SimpleTestCase):
    """The object key layout must stay test_cases/{id}/{NN} and {NN}.a."""

    def test_keys(self):
        self.assertEqual(problem_prefix(7), "test_cases/7/")
        self.assertEqual(test_input_key(7, 1), "test_cases/7/01")
        self.assertEqual(test_output_key(7, 1), "test_cases/7/01.a")
        self.assertEqual(test_input_key(7, 14), "test_cases/7/14")
        self.assertEqual(test_input_key(7, 100), "test_cases/7/100")
        self.assertEqual(problem_file_key(7, "custom_checker"), "test_cases/7/custom_checker")


class S3StorageTests(SimpleTestCase):

    def test_upload_test_case_writes_input_and_answer(self):
        storage, stub = make_s3_storage()
        stub.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "test_cases/7/01", "Body": b"1 2\n"})
        stub.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "test_cases/7/01.a", "Body": b"3\n"})
        with stub:
            storage.upload_test_case(7, 1, "1 2\n", "3\n")
        stub.assert_no_pending_responses()

    def test_delete_problem_files_deletes_only_that_prefix(self):
        storage, stub = make_s3_storage()
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "test_cases/7/01"}, {"Key": "test_cases/7/01.a"}], "KeyCount": 2, "IsTruncated": False},
            {"Bucket": BUCKET, "Prefix": "test_cases/7/"},
        )
        stub.add_response(
            "delete_objects",
            {},
            {
                "Bucket": BUCKET,
                "Delete": {"Objects": [{"Key": "test_cases/7/01"}, {"Key": "test_cases/7/01.a"}], "Quiet": True},
            },
        )
        with stub:
            self.assertEqual(storage.delete_problem_files(7), 2)
        stub.assert_no_pending_responses()

    def test_delete_with_no_objects_makes_no_delete_call(self):
        storage, stub = make_s3_storage()
        stub.add_response("list_objects_v2", {"KeyCount": 0, "IsTruncated": False}, {"Bucket": BUCKET, "Prefix": "test_cases/7/"})
        with stub:
            self.assertEqual(storage.delete_problem_files(7), 0)
        stub.assert_no_pending_responses()

    def test_upload_error_is_raised(self):
        storage, stub = make_s3_storage()
        stub.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
        with stub, self.assertRaises(Exception):
            storage.upload_file("test_cases/7/01", b"x")

    def test_missing_bucket_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            S3Storage(bucket_name="", region="us-east-1")


class GetStorageTests(SimpleTestCase):

    @override_settings(
        STORAGE_PROVIDER="s3",
        AWS_S3_BUCKET_NAME=BUCKET,
        AWS_REGION="us-east-1",
        AWS_ACCESS_KEY_ID="testing",
        AWS_SECRET_ACCESS_KEY="testing",
    )
    def test_s3_provider(self):
        storage = get_storage()
        self.assertIsInstance(storage, S3Storage)
        self.assertIsInstance(storage, TestCaseStorage)

    @override_settings(STORAGE_PROVIDER="dropbox")
    def test_unknown_provider(self):
        with self.assertRaises(ImproperlyConfigured):
            get_storage()
