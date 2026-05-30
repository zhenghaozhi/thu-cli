"""集中管理所有 HTTP endpoint。

按 domain section 分块。所有 SDK / service 模块都应该从这里导入 URL，不要在各自
文件里硬写。新加接口的 URL 也加在这里。

外部 SDK 用户拷代码时**至少**带走本文件。
"""
from __future__ import annotations

from .webvpn import webvpn_url

# ============================================================================
# id.tsinghua — 统一身份认证
# ============================================================================
ID_BASE = "https://id.tsinghua.edu.cn"

SSO_FORM_PREFIX = f"{ID_BASE}/do/off/ui/auth/login/form/"
SSO_CHECK = f"{ID_BASE}/do/off/ui/auth/login/check"
SSO_CAPTCHA_IMG = f"{ID_BASE}/captcha.jpg"
DA_LOGIN = f"{ID_BASE}/b/doubleAuth/login"          # 二次认证（FIND_APPROACHES / SEND_CODE / VERITY_CODE）
DA_SAVE_FINGER = f"{ID_BASE}/b/doubleAuth/personal/saveFinger"


def sso_form_url(app_id: str, slot: int = 0) -> str:
    """id.tsinghua 上某个 APP_ID 的登录表单页。"""
    return f"{SSO_FORM_PREFIX}{app_id}/{slot}"


# ============================================================================
# learn.tsinghua — 网络学堂
# ============================================================================
LEARN_BASE = "https://learn.tsinghua.edu.cn"
LEARN_DOMAIN = "learn.tsinghua.edu.cn"  # csrf_params() 用

LEARN_HOMEPAGE = f"{LEARN_BASE}/f/wlxt/index/course/student/"
LEARN_SEMESTER = f"{LEARN_BASE}/b/kc/zhjw_v_code_xnxq/getCurrentAndNextSemester"
LEARN_SEMESTERS = f"{LEARN_BASE}/b/wlxt/kc/v_wlkc_xs_xktjb_coassb/queryxnxq"
LEARN_ANNOUNCEMENTS = f"{LEARN_BASE}/b/wlxt/kcgg/wlkc_ggb/student/pageListbyxq"
LEARN_COURSE_ANNOUNCEMENTS = f"{LEARN_BASE}/b/wlxt/kcgg/wlkc_ggb/student/pageListXsSearch"
LEARN_COURSE_TIME_LOCATION = f"{LEARN_BASE}/b/kc/v_wlkc_xk_sjddb/detail"
LEARN_HOMEWORK_NEW = f"{LEARN_BASE}/b/wlxt/kczy/zy/student/zyListWj"
LEARN_HOMEWORK_SUBMITTED = f"{LEARN_BASE}/b/wlxt/kczy/zy/student/zyListYjwg"
LEARN_HOMEWORK_GRADED = f"{LEARN_BASE}/b/wlxt/kczy/zy/student/zyListYpg"
LEARN_HOMEWORK_DETAIL = f"{LEARN_BASE}/b/wlxt/kczy/zy/student/detail"
LEARN_HOMEWORK_SUBMIT = f"{LEARN_BASE}/b/wlxt/kczy/zy/student/tjzy"
LEARN_QNR_ONGOING = f"{LEARN_BASE}/b/wlxt/kcwj/wlkc_wjb/student/pageListWks"
LEARN_QNR_ENDED = f"{LEARN_BASE}/b/wlxt/kcwj/wlkc_wjb/student/pageListYjs"
LEARN_QNR_DETAIL = f"{LEARN_BASE}/b/wlxt/kcwj/wlkc_wjb/student/getWjnr"


def learn_course_url(course_id: str) -> str:
    return f"{LEARN_BASE}/f/wlxt/index/course/student/course?wlkcid={course_id}"


def learn_courses_by_semester_url(semester: str) -> str:
    return (f"{LEARN_BASE}/b/wlxt/kc/v_wlkc_xs_xkb_kcb_extend/student/"
            f"loadCourseBySemesterId/{semester}/zh")


def learn_course_time_location_url(course_id: str) -> str:
    return f"{LEARN_COURSE_TIME_LOCATION}?id={course_id}"


def learn_course_file_list_url(course_id: str, *, size: int = 200) -> str:
    return (f"{LEARN_BASE}/b/wlxt/kj/wlkc_kjxxb/student/"
            f"kjxxbByWlkcidAndSizeForStudent?wlkcid={course_id}&size={size}")


def learn_course_file_download_url(file_id: str) -> str:
    return f"{LEARN_BASE}/b/wlxt/kj/wlkc_kjxxb/student/downloadFile?sfgk=0&wjid={file_id}"


def learn_course_file_categories_url(course_id: str) -> str:
    return f"{LEARN_BASE}/b/wlxt/kj/wlkc_kjflb/student/pageList?wlkcid={course_id}"


def learn_course_files_by_category_url(course_id: str, category_id: str) -> str:
    return f"{LEARN_BASE}/b/wlxt/kj/wlkc_kjxxb/student/kjxxb/{course_id}/{category_id}"


def learn_announcement_view_url(course_id: str, announcement_id: str) -> str:
    """公告 HTML 详情页。注意：访问可能将公告标记为已读。"""
    return (f"{LEARN_BASE}/f/wlxt/kcgg/wlkc_ggb/student/beforeViewXs"
            f"?wlkcid={course_id}&id={announcement_id}")


def learn_preview_url(file_id: str, *, module: str = "mk_kcgg") -> str:
    """通用预览页；mk 取值随模块变化：公告附件 ``mk_kcgg`` / 课件 ``mk_kcwj`` / 作业 ``mk_kczy``。"""
    return (f"{LEARN_BASE}/f/wlxt/kc/wj_wjb/student/beforePlay"
            f"?wjid={file_id}&mk={module}&browser=-1&sfgk=0&pageType=all")


def learn_homework_page_url(course_id: str, homework_id: str) -> str:
    return f"{LEARN_BASE}/f/wlxt/kczy/zy/student/viewCj?wlkcid={course_id}&xszyid={homework_id}"


def learn_homework_submit_url(course_id: str, homework_id: str) -> str:
    return f"{LEARN_BASE}/f/wlxt/kczy/zy/student/tijiao?wlkcid={course_id}&xszyid={homework_id}"


def learn_homework_download_url(course_id: str, attachment_id: str) -> str:
    return f"{LEARN_BASE}/b/wlxt/kczy/zy/student/downloadFile/{course_id}/{attachment_id}"


def learn_discussion_list_url(course_id: str, *, size: int = 200) -> str:
    return f"{LEARN_BASE}/b/wlxt/bbs/bbs_tltb/student/kctlList?wlkcid={course_id}&size={size}"


def learn_discussion_url(course_id: str, board_id: str, discussion_id: str, *, tab_id: int = 1) -> str:
    return (f"{LEARN_BASE}/f/wlxt/bbs/bbs_tltb/student/viewTlById"
            f"?wlkcid={course_id}&id={discussion_id}&tabbh={tab_id}&bqid={board_id}")


def learn_answered_question_list_url(course_id: str, *, size: int = 200) -> str:
    return f"{LEARN_BASE}/b/wlxt/bbs/bbs_tltb/student/kcdyList?wlkcid={course_id}&size={size}"


def learn_answered_question_url(course_id: str, question_id: str) -> str:
    return f"{LEARN_BASE}/f/wlxt/bbs/bbs_kcdy/student/viewDyById?wlkcid={course_id}&id={question_id}"


def learn_questionnaire_url(course_id: str, questionnaire_id: str, questionnaire_type: str) -> str:
    return (f"{LEARN_BASE}/f/wlxt/kcwj/wlkc_wjb/student/beforeAdd"
            f"?wlkcid={course_id}&wjid={questionnaire_id}&wjlx={questionnaire_type}&jswj=no")


# ============================================================================
# info portal（webvpn realm 内）
# ============================================================================
# 我们 target ``info.tsinghua.edu.cn`` 而非 thu-info-lib 硬编的 ``info2021``：
#   - id.tsinghua 的 INFO_PORTAL APP_ID redirect_uri 落到 info.tsinghua，bootstrap 在这里拿 cookie
#   - 经验证 wengine-vpn/cookie?host=info.tsinghua 返回有效 XSRF-TOKEN；host=info2021 会被
#     onlineAppRedirect 以 "用户未登录" 拒绝
INFO_ROAMING_URL = webvpn_url(
    "info.tsinghua.edu.cn",
    "/b/yyfw/vyyfwxx/info/portal_fg/common/onlineAppRedirect",
)
INFO_CALENDAR_URL = webvpn_url(
    "info.tsinghua.edu.cn",
    "/b/info/gxfw_fg/common/xl",
)
INFO_USER_DATA_URL = webvpn_url(
    "info.tsinghua.edu.cn",
    "/b/info/gxfw_fg/common/grjbxx",
)
# 特殊：webvpn 的 cookie-bridge endpoint。返回内网 host 的 cookie 作为纯字符串。
# 我们从中 grep XSRF-TOKEN 作为 info portal 的 csrf。
INFO_CSRF_COOKIE_URL = (
    "https://webvpn.tsinghua.edu.cn/wengine-vpn/cookie?method=get"
    "&host=info.tsinghua.edu.cn&scheme=https&path=/f/info/gxfw_fg/common/index"
)

# ============================================================================
# zhjw — 教务（成绩单 / 课程表）。zhjw 只走 HTTP，所以 scheme="http"。
# ============================================================================
ZHJW_TRANSCRIPT_BKS_URL = webvpn_url(
    "zhjw.cic.tsinghua.edu.cn",
    "/cj.cjCjbAll.do?m=bks_cjdcx&cjdlx=zw",
    scheme="http",
)
ZHJW_TRANSCRIPT_YJS_URL = webvpn_url(
    "zhjw.cic.tsinghua.edu.cn",
    "/cj.cjCjbAll.do?m=yjs_cjdcx&cjdlx=zw",
    scheme="http",
)

# 课程表是 JSONP；URL 拼成 ``<prefix><start>&p_end_date=<end>&jsoncallback=m``
ZHJW_TIMETABLE_BKS_PREFIX = webvpn_url(
    "zhjw.cic.tsinghua.edu.cn",
    "/jxmh_out.do?m=bks_jxrl_all&p_start_date=",
    scheme="http",
)
ZHJW_TIMETABLE_YJS_PREFIX = webvpn_url(
    "zhjw.cic.tsinghua.edu.cn",
    "/jxmh_out.do?m=yjs_jxrl_all&p_start_date=",
    scheme="http",
)
ZHJW_TIMETABLE_MIDDLE = "&p_end_date="
ZHJW_TIMETABLE_SUFFIX = "&jsoncallback=m"


__all__ = [
    "DA_LOGIN", "DA_SAVE_FINGER",
    "ID_BASE",
    "INFO_CALENDAR_URL", "INFO_CSRF_COOKIE_URL", "INFO_ROAMING_URL", "INFO_USER_DATA_URL",
    "LEARN_ANNOUNCEMENTS", "LEARN_BASE", "LEARN_COURSE_ANNOUNCEMENTS",
    "LEARN_COURSE_TIME_LOCATION", "LEARN_DOMAIN", "LEARN_HOMEPAGE",
    "LEARN_HOMEWORK_DETAIL", "LEARN_HOMEWORK_GRADED", "LEARN_HOMEWORK_NEW",
    "LEARN_HOMEWORK_SUBMIT", "LEARN_HOMEWORK_SUBMITTED",
    "LEARN_QNR_DETAIL", "LEARN_QNR_ENDED", "LEARN_QNR_ONGOING",
    "LEARN_SEMESTER", "LEARN_SEMESTERS",
    "SSO_CAPTCHA_IMG", "SSO_CHECK", "SSO_FORM_PREFIX",
    "ZHJW_TIMETABLE_BKS_PREFIX", "ZHJW_TIMETABLE_MIDDLE", "ZHJW_TIMETABLE_SUFFIX",
    "ZHJW_TIMETABLE_YJS_PREFIX", "ZHJW_TRANSCRIPT_BKS_URL", "ZHJW_TRANSCRIPT_YJS_URL",
    "learn_announcement_view_url", "learn_answered_question_list_url", "learn_answered_question_url",
    "learn_course_file_categories_url", "learn_course_file_download_url",
    "learn_course_file_list_url", "learn_course_files_by_category_url",
    "learn_course_time_location_url", "learn_course_url",
    "learn_courses_by_semester_url", "learn_discussion_list_url", "learn_discussion_url",
    "learn_homework_download_url", "learn_homework_page_url", "learn_homework_submit_url",
    "learn_preview_url", "learn_questionnaire_url",
    "sso_form_url",
]
