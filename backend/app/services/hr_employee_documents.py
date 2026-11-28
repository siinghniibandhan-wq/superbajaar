"""Private S3 storage for HR employee documents."""
from __future__ import annotations
import hashlib, os, re, uuid, socket, struct
import boto3

MAX_BYTES=10*1024*1024
ALLOWED={
 "application/pdf":("pdf",b"%PDF-"),
 "image/jpeg":("jpg",bytes((0xff,0xd8,0xff))),
 "image/png":("png",bytes((0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a))),
}
class EmployeeDocumentError(ValueError): pass
class EmployeeDocumentConfigurationError(RuntimeError): pass

def _storage():
 bucket=os.getenv("SB_PRIVATE_DOCUMENT_BUCKET","").strip()
 region=os.getenv("SB_S3_REGION","").strip() or os.getenv("AWS_REGION","").strip()
 if not bucket or not region: raise EmployeeDocumentConfigurationError("Private employee document storage is not configured")
 return bucket,boto3.client("s3",region_name=region)

def scan_employee_document(content:bytes)->str:
 host=os.getenv("SB_DOCUMENT_CLAMAV_HOST","").strip()
 if not host:
  raise EmployeeDocumentConfigurationError("Employee document malware scanning is not configured; set SB_DOCUMENT_CLAMAV_HOST")
 try:
  port=int(os.getenv("SB_DOCUMENT_CLAMAV_PORT","3310"))
  timeout=float(os.getenv("SB_DOCUMENT_CLAMAV_TIMEOUT_SECONDS","10"))
  if not 1<=port<=65535 or not 1<=timeout<=60: raise ValueError
 except ValueError as exc:
  raise EmployeeDocumentConfigurationError("Employee document malware scanner configuration is invalid") from exc
 try:
  with socket.create_connection((host,port),timeout=timeout) as client:
   client.settimeout(timeout)
   client.sendall(b"zINSTREAM\0")
   for offset in range(0,len(content),65536):
    chunk=content[offset:offset+65536]
    client.sendall(struct.pack("!I",len(chunk))+chunk)
   client.sendall(struct.pack("!I",0))
   response=client.recv(4096).decode("utf-8","replace").strip()
 except OSError as exc:
  raise EmployeeDocumentConfigurationError("Employee document malware scanner is unavailable; upload was blocked") from exc
 if response.endswith("OK"):
  return "clean"
 if "FOUND" in response:
  raise EmployeeDocumentError("The uploaded document was detected as malware and was rejected")
 raise EmployeeDocumentConfigurationError("Employee document malware scanner returned an invalid response; upload was blocked")

def upload_employee_document(*,employee_id:int,uploader_id:int,document_type:str,file_name:str,content_type:str,content:bytes)->dict:
 if employee_id<=0 or uploader_id<=0: raise EmployeeDocumentError("Valid employee and uploader are required")
 if document_type not in {"identity","address","qualification","employment","contract","policy_acknowledgement","other"}:
  raise EmployeeDocumentError("Unsupported employee document type")
 if content_type not in ALLOWED: raise EmployeeDocumentError("Upload a PDF, JPEG or PNG document")
 if not content or len(content)>MAX_BYTES: raise EmployeeDocumentError("Document must be between 1 byte and 10 MB")
 extension,signature=ALLOWED[content_type]
 if not content.startswith(signature): raise EmployeeDocumentError("File content does not match its declared type")
 safe_name=re.sub(r"[^A-Za-z0-9._-]","_",os.path.basename(file_name))[:160] or "document"
 digest=hashlib.sha256(content).hexdigest()
 scan_status=scan_employee_document(content)
 bucket,client=_storage()
 key=f"hr-employee-documents/{employee_id}/{uuid.uuid4().hex}.{extension}"
 client.put_object(Bucket=bucket,Key=key,Body=content,ContentType=content_type,
  ServerSideEncryption="AES256",Metadata={"employee-id":str(employee_id),"uploaded-by-user-id":str(uploader_id),"sha256":digest,"document-type":document_type,"file-name":safe_name,"malware-scan":scan_status})
 return {"object_key":key,"file_name":safe_name,"content_type":content_type,"file_size_bytes":len(content),"sha256":digest,"document_type":document_type,"malware_scan_status":scan_status}

def delete_employee_document(*,employee_id:int,object_key:str)->None:
 if employee_id<=0 or not re.fullmatch(r"hr-employee-documents/\d+/[0-9a-f]{32}\.(pdf|jpg|png)",object_key or "") or not object_key.startswith(f"hr-employee-documents/{employee_id}/"):
  raise EmployeeDocumentError("Document is outside this employee's private storage area")
 bucket,client=_storage()
 head=client.head_object(Bucket=bucket,Key=object_key)
 metadata=head.get("Metadata",{})
 if metadata.get("employee-id")!=str(employee_id) or head.get("ServerSideEncryption")!="AES256":
  raise EmployeeDocumentError("Document ownership or encryption validation failed")
 client.delete_object(Bucket=bucket,Key=object_key)


def employee_document_download_url(*,employee_id:int,object_key:str,expires_in:int=300)->str:
 if employee_id<=0 or not 60<=expires_in<=600: raise EmployeeDocumentError("Invalid employee document download request")
 if not re.fullmatch(r"hr-employee-documents/\d+/[0-9a-f]{32}\.(pdf|jpg|png)",object_key or "") or not object_key.startswith(f"hr-employee-documents/{employee_id}/"):
  raise EmployeeDocumentError("Document is outside this employee's private storage area")
 bucket,client=_storage()
 head=client.head_object(Bucket=bucket,Key=object_key)
 metadata=head.get("Metadata",{})
 if metadata.get("employee-id")!=str(employee_id) or head.get("ServerSideEncryption")!="AES256":
  raise EmployeeDocumentError("Document ownership or encryption validation failed")
 return client.generate_presigned_url("get_object",Params={"Bucket":bucket,"Key":object_key},ExpiresIn=expires_in)
