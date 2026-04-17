import os
import threading
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

_SCOPES      = ["https://www.googleapis.com/auth/drive.file"]
_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OAUTH_CLIENT = os.path.join(_BASE_DIR, "oauth_client.json")
_TOKEN_FILE   = os.path.join(_BASE_DIR, "token.json")

# Serialise token refresh + uploads so concurrent jobs don't corrupt token.json
_drive_lock = threading.Lock()


def _get_drive_service():
    """Return an authenticated Drive service using OAuth2 (user account)."""
    creds = None
    if os.path.exists(_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(_TOKEN_FILE, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(_OAUTH_CLIENT):
                raise RuntimeError("oauth_client.json not found — add OAuth credentials to the project folder")
            flow = InstalledAppFlow.from_client_secrets_file(_OAUTH_CLIENT, _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def upload_to_drive(local_pdf_path: str, filename: str,
                    folder_id: str | None = None,
                    mimetype: str = "application/pdf",
                    public: bool | None = None) -> str:
    """Upload file to Drive via OAuth user account. Returns shareable URL."""
    with _drive_lock:
        return _upload(local_pdf_path, filename, folder_id, mimetype, public)


def _upload(local_path: str, filename: str,
            folder_id: str | None,
            mimetype: str,
            public: bool | None) -> str:
    service = _get_drive_service()

    folder_id = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    metadata: dict = {"name": filename}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(local_path, mimetype=mimetype, resumable=True)
    file_obj = service.files().create(body=metadata, media_body=media, fields="id").execute()
    file_id = file_obj["id"]

    if public is None:
        public = os.environ.get("GOOGLE_DRIVE_PUBLIC", "true").lower() == "true"
    if public:
        service.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"}
        ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"


def upload_tex_to_drive(local_tex_path: str, filename: str) -> str:
    """Upload .tex source to the separate tex folder (GOOGLE_DRIVE_TEX_FOLDER_ID).

    Falls back to GOOGLE_DRIVE_FOLDER_ID if the tex-specific env isn't set.
    Uses text/x-tex so Drive shows it as text, not binary.
    """
    tex_folder = (os.environ.get("GOOGLE_DRIVE_TEX_FOLDER_ID")
                  or os.environ.get("GOOGLE_DRIVE_FOLDER_ID"))
    return upload_to_drive(local_tex_path, filename,
                           folder_id=tex_folder,
                           mimetype="text/x-tex",
                           public=False)
