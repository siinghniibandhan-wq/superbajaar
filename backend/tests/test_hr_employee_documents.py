import pytest
from app.services import hr_employee_documents as docs


class FakeS3:
    def __init__(self):
        self.objects={}
    def put_object(self,**kwargs):
        self.objects[kwargs["Key"]]=kwargs
    def head_object(self,**kwargs):
        item=self.objects[kwargs["Key"]]
        return {"Metadata":item["Metadata"],"ServerSideEncryption":item["ServerSideEncryption"]}
    def generate_presigned_url(self,*args,**kwargs):
        return "https://private.example.test/short-lived"


def test_employee_document_upload_uses_private_encrypted_employee_scoped_key(monkeypatch):
    fake=FakeS3()
    monkeypatch.setattr(docs,"_storage",lambda:("private-bucket",fake))
    monkeypatch.setattr(docs,"scan_employee_document",lambda content:"clean")
    result=docs.upload_employee_document(
        employee_id=42,uploader_id=7,document_type="identity",
        file_name="../../identity proof.pdf",content_type="application/pdf",
        content=b"%PDF-1.7 test"
    )
    assert result["object_key"].startswith("hr-employee-documents/42/")
    assert result["file_name"]=="identity_proof.pdf"
    stored=fake.objects[result["object_key"]]
    assert stored["ServerSideEncryption"]=="AES256"
    assert stored["Metadata"]["employee-id"]=="42"
    assert stored["Metadata"]["uploaded-by-user-id"]=="7"
    assert len(result["sha256"])==64
    assert result["malware_scan_status"]=="clean"


def test_employee_document_upload_rejects_mime_signature_mismatch():
    with pytest.raises(docs.EmployeeDocumentError,match="does not match"):
        docs.upload_employee_document(
            employee_id=42,uploader_id=7,document_type="identity",
            file_name="bad.pdf",content_type="application/pdf",content=b"not a pdf"
        )


def test_employee_document_upload_rejects_unsupported_document_type():
    with pytest.raises(docs.EmployeeDocumentError,match="Unsupported"):
        docs.upload_employee_document(
            employee_id=42,uploader_id=7,document_type="secret",
            file_name="id.pdf",content_type="application/pdf",content=b"%PDF-1.7"
        )


def test_employee_document_download_checks_owner_and_encryption(monkeypatch):
    fake=FakeS3()
    monkeypatch.setattr(docs,"_storage",lambda:("private-bucket",fake))
    result=docs.upload_employee_document(
        employee_id=42,uploader_id=7,document_type="contract",
        file_name="contract.pdf",content_type="application/pdf",content=b"%PDF-1.7"
    )
    url=docs.employee_document_download_url(employee_id=42,object_key=result["object_key"])
    assert url=="https://private.example.test/short-lived"
    with pytest.raises(docs.EmployeeDocumentError,match="outside"):
        docs.employee_document_download_url(employee_id=43,object_key=result["object_key"])
