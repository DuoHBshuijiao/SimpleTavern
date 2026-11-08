"""每次运行时生成测试凭据，不进仓库。"""
import json
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def private_key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode("ascii")


def public_key_pem(key):
    return key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def service_account_info(pem, token_uri):
    """字段和 Google 服务账号 JSON 一致。"""
    return {
        "type": "service_account",
        "project_id": "p",
        "private_key_id": secrets.token_hex(20),
        "private_key": pem,
        "client_email": "api-check@p.iam.gserviceaccount.com",
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": token_uri,
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/api-check%40p.iam.gserviceaccount.com",
        "universe_domain": "googleapis.com",
    }


def bedrock_api_key():
    # 长期 Bedrock API Key 以 ABSK 开头。写成接近真实的形状，打码规则才有机会识别它。
    return "ABSK" + secrets.token_urlsafe(48)


def mistral_api_key():
    return secrets.token_urlsafe(24).replace("-", "a").replace("_", "b")


def private_key_fragments(pem):
    """私钥正文的片段：完整 PEM、JSON 转义后的 PEM、中间一段。"""
    body = "".join(line for line in pem.splitlines() if "PRIVATE KEY" not in line)
    return [pem, json.dumps(pem)[1:-1], body[100:160], "PRIVATE KEY-----"]
