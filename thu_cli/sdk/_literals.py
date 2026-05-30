"""Server-side literals used by Tsinghua web endpoints.

These strings are not UI copy. They are request values, response markers, or
HTML labels emitted by upstream services, so they stay in the SDK instead of
the CLI i18n catalog.
"""

SERVER_YES = "是"
SERVER_NO = "否"

SSO_BAD_CREDENTIALS_MARKER = "不正确"
SSO_DOUBLE_AUTH_MARKER = "二次认证"
SSO_LOGIN_SUCCESS_MARKER = "登录成功"
SSO_NOT_LOGGED_IN_MARKER = "未登录"
SSO_NO_PERMISSION_MARKER = "无权限"
SSO_TRUST_DEVICE_LIMIT_MARKER = "上限"

INFO_LOGIN_FORM_MARKER = "请输入帐号"
INFO_TOTAL_CREDIT_LABEL = "总学分"
INFO_AVERAGE_GPA_PREFIX = "平均学分绩"
INFO_NON_GPA_GRADES = {"通过", "合格", "不合格", "免修"}

LEARN_EXPIRED_MARKER = "已过期"
LEARN_OPEN_TIME_VALUE = "时间不限"
LEARN_SUCCESS_SUFFIX = "成功"

__all__ = [
    "INFO_AVERAGE_GPA_PREFIX",
    "INFO_LOGIN_FORM_MARKER",
    "INFO_NON_GPA_GRADES",
    "INFO_TOTAL_CREDIT_LABEL",
    "LEARN_EXPIRED_MARKER",
    "LEARN_OPEN_TIME_VALUE",
    "LEARN_SUCCESS_SUFFIX",
    "SERVER_NO",
    "SERVER_YES",
    "SSO_BAD_CREDENTIALS_MARKER",
    "SSO_DOUBLE_AUTH_MARKER",
    "SSO_LOGIN_SUCCESS_MARKER",
    "SSO_NOT_LOGGED_IN_MARKER",
    "SSO_NO_PERMISSION_MARKER",
    "SSO_TRUST_DEVICE_LIMIT_MARKER",
]
