"""Local file storage client for Chainlit element persistence."""
import os
import aiofiles
from chainlit.data.storage_clients.base import BaseStorageClient

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class LocalStorageClient(BaseStorageClient):
    async def upload_file(self, object_key, data, mime="application/octet-stream", overwrite=True, content_disposition=None):
        path = os.path.join(UPLOAD_DIR, object_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data.encode() if isinstance(data, str) else data)
        return {"object_key": object_key, "url": f"/uploads/{object_key}"}

    async def delete_file(self, object_key):
        path = os.path.join(UPLOAD_DIR, object_key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    async def get_read_url(self, object_key):
        return f"/uploads/{object_key}"

    async def close(self):
        pass
