from pydantic import BaseModel, ConfigDict, Field


# KIS 조회 API는 기본 UA를 거르는 경우가 있어 브라우저 UA를 실어 보낸다.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


class KISBaseModel(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)


class KISQueryHeaders(KISBaseModel):
    """KIS REST 조회 API 공통 요청 헤더.

    TR ID만 다르고 나머지가 같은 조회 API가 계속 늘어나므로 헤더 모델을 공용으로 둔다.
    """

    content_type: str = Field(serialization_alias="Content-Type", default="application/json")
    accept: str = Field(serialization_alias="Accept", default="text/plain")
    charset: str = "UTF-8"
    user_agent: str = Field(serialization_alias="User-Agent", default=DEFAULT_USER_AGENT)
    authorization: str
    app_key: str = Field(serialization_alias="appkey")
    app_secret: str = Field(serialization_alias="appsecret")
    tr_id: str
    customer_type: str = Field(serialization_alias="custtype", default="P")
    tr_cont: str = ""
