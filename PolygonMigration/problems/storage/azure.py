"""
Azure Blob Storage implementation of TestCaseStorage.

This is the original AzureBlobManager logic (previously problems/AzureTestcase.py)
moved behind the TestCaseStorage interface. Authentication is unchanged:
username/password credential against an Azure AD app.

Configuration (environment variables, read in settings.py):
    AZURE_STORAGE_ACCOUNT_URL, AZURE_TENANT_ID, AZURE_CLIENT_ID,
    AZURE_USERNAME, AZURE_PASSWORD, AZURE_CONTAINER_NAME
"""
import logging

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import UsernamePasswordCredential
from azure.storage.blob import BlobServiceClient

from .base import TestCaseStorage, problem_prefix

logger = logging.getLogger(__name__)


class AzureBlobStorage(TestCaseStorage):
    display_name = "Azure Blob Storage"

    def __init__(self, account_url, tenant_id, client_id, username, password, container_name):
        self.container_name = container_name
        logger.info("Attempting to authenticate with Azure...")
        try:
            credential = UsernamePasswordCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                username=username,
                password=password,
            )
            self.blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
        except ClientAuthenticationError:
            logger.warning(
                "Azure authentication failed. Check username, password, tenant_id and client_id. "
                "This method may not work if Multi-Factor Authentication (MFA) is enabled for the user."
            )
            raise
        logger.info("Authentication successful. BlobServiceClient created.")

    @classmethod
    def from_settings(cls, settings):
        return cls(
            account_url=settings.AZURE_STORAGE_ACCOUNT_URL,
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            username=settings.AZURE_USERNAME,
            password=settings.AZURE_PASSWORD,
            container_name=settings.AZURE_CONTAINER_NAME,
        )

    def upload_file(self, key, data):
        blob_client = self.blob_service_client.get_blob_client(container=self.container_name, blob=key)
        blob_client.upload_blob(data, overwrite=True)
        logger.info("Uploaded blob %s/%s (%d bytes)", self.container_name, key, len(data))

    def delete_problem_files(self, problem_id):
        prefix = problem_prefix(problem_id)
        container_client = self.blob_service_client.get_container_client(self.container_name)
        names = [blob.name for blob in container_client.list_blobs(name_starts_with=prefix)]
        for name in names:
            logger.info("Deleting blob: %s", name)
            container_client.delete_blob(name)
        logger.info("Deleted %d blob(s) under %s/%s", len(names), self.container_name, prefix)
        return len(names)
