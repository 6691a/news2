from pydantic import Field

from app.kis.schemas.common import KISBaseModel


class KISBaseAuthTokenHeader(KISBaseModel):
    content_type: str = Field(serialization_alias="Content-Type", default="application/json")
    accept: str = Field(serialization_alias="Accept", default="text/plain")
    charset: str = "UTF-8"


class KISBaseAuthRequest(KISBaseModel):
    app_key: str = Field(serialization_alias="appkey", max_length=36)
    app_secret: str = Field(serialization_alias="appsecret", max_length=180)


class KISAuthRequest(KISBaseAuthRequest):
    grant_type: str = "client_credentials"


class KISAuthTokenResponse(KISBaseModel):
    access_token: str
    token_type: str
    expires_in: float
    access_token_token_expired: str


class KISAuthTokenRemoveRequest(KISBaseAuthRequest):
    token: str = Field()


class KISAuthTokenRemoveResponse(KISBaseModel):
    code: int
    message: str


class KISWebSocketTokenRequest(KISAuthRequest):
    app_secret: str = Field(serialization_alias="secretkey", max_length=180)


class KISWebSocketTokenResponse(KISBaseModel):
    approval_key: str
