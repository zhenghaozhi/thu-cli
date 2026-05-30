# thu-cli

清华统一认证 + 网络学堂 + 信息门户的 Python CLI 和 SDK。**不复刻网页 GUI**——目标是把清华各内网服务整理成稳定、脚本友好、agent 友好的接口。

- **协议透明**：所有 HTTP 行为可观测、可控；session / device / 2FA / 验证码全部走显式回调
- **多账号 profile**：本地维护多账号，session 复用，不存密码
- **跨课程并发**：service 层一次请求拉跨课程聚合结果，部分失败收成 warning 不阻断
- **架构守恒**：分层边界、命名约定、扩展契约由 architecture tests 钉死
- **多 realm + 多 CampusApp**：一份凭证 bootstrap learn / webvpn 任意 realm；webvpn 内的 info portal / transcript / timetable 按需 lazy bootstrap
- **可热插拔**：外部应用只想用部分功能时，最少拷 **2 个目录**（`core/` + `sdk/`）即可独立运行；见下方 [extraction guide](#extraction-guide)

当前覆盖：

- **统一认证**：密码 + 2FA + 信任设备 + 两阶段登录
- **网络学堂**（learn realm）：用户信息 / 课程 / 公告 / 课件 / 作业 / 讨论 / 答疑 / 问卷；统一下载（`RemoteFile`）；学生侧作业提交
- **信息门户**（webvpn realm）：教学日历 / 历年成绩单 / 课程表（本科 + 研究生）

**不包含**：教师 / TA 模式、选课写操作、体育馆预约、校园卡写操作、密码本地存储。

`campus/` 与 `academic/` 是预留扩展位置（电费 / 网费 / 图书馆 / 校园卡 / 教室 / 培养方案 / 考试 / 窥分），按 [扩展指南](#扩展指南) 加命令文件即可。

---

## 项目状态

- 包名：`thu-cli`
- 当前版本：`0.2.0`
- Python：`>=3.10`
- 命令入口：`thu`
- 许可证：MIT，见 [LICENSE](LICENSE)

这是 `thu-cli` 的重构主线版本。公共入口保持为 `thu` / `thu_cli`，内部按 `core -> sdk -> services -> cli` 分层，便于外部项目只抽取底层 SDK。清华站点接口可能变动，涉及线上站点的能力以 live 测试和实际登录结果为准。

---

## 安装

```bash
git clone <repo>
cd thu-cli
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

入口：

- 命令行 `thu`（自动注册 `console_scripts`）
- Python 包 `thu_cli`
- 也可 `python3 -m thu_cli ...`

只作为最终用户安装时，不需要 dev 依赖：

```bash
python3 -m pip install .
```

升级旧本地安装时建议先卸载再重新安装，避免同名入口残留旧 editable 路径：

```bash
python3 -m pip uninstall -y thu-cli
python3 -m pip install -e .
```

本地数据默认写到 `~/.config/thu-cli`，可用 `THU_CLI_HOME=/path/to/dir` 覆盖。目录结构：

```text
$THU_CLI_HOME/
  config.json
  users/<id>/
    session.json
    device.json
    stage.json
    last_captcha.jpg
```

其中 `session.json` / `device.json` / `stage.json` 会按 0600 权限写入；profile 不保存密码。

---

## 60 秒上手

### Python（推荐路径——脚本 / agent / MCP）

```python
from thu_cli import LearnService, AuthInteraction

service = LearnService()
listing = service.list_homeworks(
    interaction=AuthInteraction(passwd_fn=lambda: "your-password"),
)
for hw in listing.items:
    print(hw.deadline, hw.course_name, hw.title)
for w in listing.warnings:
    print(w.context, w.message)        # context 是 course_id
```

### CLI

```bash
thu auth use 2023012168            # 选 / 创建当前 profile（不登录）
thu auth login                     # 显式登录（含 2FA 流程）
thu learn course                   # 本学期课程
thu learn announcement --unread    # 未读公告
thu info calendar                  # 教学日历
thu info transcript                # 历年成绩 + GPA
```

无参数 `thu` 进入交互式 shell。

---

## CLI 用法

输出统一前缀 `[info]` / `[warning]` / `[error]` / `[success]`，写 stdout / stderr 分流。
全局 `--json` 切 JSON 输出（agent 用）。全局 `-v / --verbose` 等价 `THU_CLI_LOG=DEBUG`。
文案默认随 `$LANG`，`THU_CLI_LANG=zh|en` 强制覆盖。

```
thu [-v] [--json] <domain> <command> [args]

domain: auth / learn / info / campus / academic
```

### `thu auth` — 统一认证

profile 只存账号 ID 和文件位置，**不存密码**。

```bash
thu auth use <id>                                # 切 / 创建当前 profile
thu auth whoami
thu auth profile list / add / remove
thu auth profile add <id> --current --student-type undergraduate

thu auth login [--user <id>] [--force]           # 登录并预热当前支持的服务
              [--prefer-2fa wechat|mobile|totp]
              [--trust-device ask|yes|no]
              [--no-single-login]
              [--student-type undergraduate|graduate]
thu auth verify                                  # ping learn API
thu auth status [--offline]                      # 本地状态 + 多服务远程状态
thu auth logout [--all]                          # --all 同时删 device.json
```

`thu auth login` 在一次登录中预热当前支持的只读服务：learn、webvpn、info portal，以及按 `student-type` 选择的 transcript/timetable CampusApp。

两阶段登录（适合脚本 / 外部程序接管验证码）：

```bash
thu auth login --user 2023012168 --stage send --prefer-2fa wechat
thu auth login --stage verify --code 123456
```

网络参数（适用于所有命令）：`--verify-tls` / `--no-env-proxy`。

### `thu learn` — 网络学堂

默认当前 profile + 当前学期。统一范围参数：

| 参数 | 含义 |
|---|---|
| `--user 2023012168` | 切到指定 profile |
| `--course <wlkcid>` | 限定单门课程 |
| `--semester 2025-2026-1` | 指定学期 |
| `--all` | 跨所有学期 |
| `--strict` | 任何课程拉取失败立即报错（默认收 warning 不阻断） |

```bash
thu learn me                                          # 用户信息
thu learn course [--with-time-location]
thu learn announcement [<ggid>]
                       [--unread] [--with-attachments]
                       [--download-attachments --dir downloads]
thu learn file [<wjid>]
               [--categories | --category <kjflid>]
               [--dir downloads]
thu learn homework [<xszyid>]
                   [--download | --submit]
                   [--content "..." | --content-file answer.html]
                   [--attach answer.pdf]
                   [--yes]
thu learn discussion
thu learn question
thu learn questionnaire [--with-detail]
```

**写操作语义**：`--submit` 在交互式终端会二次确认，非交互环境必须显式 `--yes`。
**SessionExpired 自动重登**对读操作生效；`submit_homework` 保守地不重试以避免重复提交。

### `thu info` — 信息门户 / zhjw

走 webvpn realm。第一次使用任意 `thu info` 子命令时，会触发 webvpn realm + INFO_PORTAL + 对应 CampusApp 的 lazy bootstrap。

```bash
thu info calendar                                    # 本学期首日 + 教学周数
thu info transcript [--undergraduate|--graduate]    # 历年成绩 + 官方/明细 GPA
thu info timetable [--start YYYY-MM-DD]
                   [--end YYYY-MM-DD]
                   [--undergraduate|--graduate]      # 课程表 + 考试日历
```

不传 `--start` / `--end` 时，timetable 默认覆盖本学期。
`--undergraduate` / `--graduate` 临时覆盖当前 profile 的 student-type。

---

## Python SDK

三层接口，按抽象高低排：

### 1. Service 层（推荐）

`LearnService` / `InfoService` 复用 CLI 的 profile / session、自动 SessionExpired 重登、跨课程并发拉取 + warning 收集。

```python
from thu_cli import LearnService, AuthInteraction

service = LearnService()
auth = dict(interaction=AuthInteraction(passwd_fn=lambda: "your-password"))

# 读：自动 SessionExpired 重登；部分课程失败收成 warning
listing = service.list_announcements(include_content=True, **auth)
for ann in listing.items:
    print(ann.published_at, ann.course_name, ann.title)
for w in listing.warnings:
    print(w.context, w.message)        # context 是 course_id

# 跨课程统一枚举（一个调用拿到公告 + 课件 + 作业 + ...）
contents = service.list_contents(
    course_id="2025-2026-2151370030",
    kinds=["announcement", "file", "homework"],
    **auth,
)

# 下载
download = service.download_course_file(None, "<wjid>", course_id="...", **auth)

# 写：保守不自动重试，SessionExpired 直接传播
service.submit_homework(None, "<xszyid>",
                        content="done",
                        attachment="answer.pdf",
                        **auth)
```

`AuthInteraction` 是 5 个交互回调的 frozen dataclass：`passwd_fn / on_2fa_choice / on_code / on_captcha / trust_device`。
`AuthNetwork` 管 `verify_tls / trust_env / debug_dir / on_event`；
`AuthPolicy` 管 `prefer_2fa / single_login / single_login_key / force_login`。

所有 listing 形状一致：`CourseScopedListing[T]` = `user + semester + courses + items + warnings`，配 `by_course()` / `course_by_id()` 工具方法。

`InfoService`：

```python
from thu_cli import InfoService, AuthInteraction

service = InfoService()
auth = dict(interaction=AuthInteraction(passwd_fn=lambda: "your-password"))

cal = service.get_calendar(**auth)
transcript = service.get_transcript_detail(graduate=None, **auth)
events = service.get_timetable(**auth)                    # 默认本学期
```

### 2. Client 层

```python
from thu_cli import SsoSession, LearnClient, InfoClient, AuthInteraction
from thu_cli.core import LEARN_REALM, INFO_PORTAL
from pathlib import Path

# 自己 bootstrap session：
sso = SsoSession()
sso.username = "2023012168"
sso.device = ... # 自己持久化
sso.ensure_realm(LEARN_REALM, interaction=AuthInteraction(passwd_fn=lambda: pw))

learn = LearnClient(sso)
print(learn.user_info().name)

# webvpn 应用：
sso.ensure_app(INFO_PORTAL, interaction=...)
print(InfoClient(sso).get_calendar())
```

### 3. SsoSession（最底层）

只表达 SSO 协议状态。两阶段 2FA 抛 `TwoFactorPending`，由调用方决定如何持久化 stage 状态：

```python
from thu_cli import SsoSession, AuthInteraction, TwoFactorPending
from thu_cli.core import LEARN_REALM

try:
    sso.ensure_realm(LEARN_REALM, defer_2fa=True, interaction=...)
except TwoFactorPending as pending:
    save_to_disk(pending.to_dict())
    # ... 后来 ...
    code = ask_user()
    sso.resume_2fa(LEARN_REALM, pending.choice, code, interaction=...)
```

---

## 架构

```
thu_cli/
  core/                        数据 / 纯函数 / URL 常量；零外部依赖
    errors.py                  全部异常类
    realms.py                  Realm 定义
    apps.py                    CampusApp 定义
    endpoints.py               URL 常量与拼装
    webvpn.py                  WEBVPN_HOST_HASH + URL 改写
  sdk/                         协议引擎；只依赖 core + requests + bs4 + gmssl
    transport.py               UA / csrf / json_or_expired / RemoteFile / stream_download
    auth.py                    SsoSession + Device + AuthInteraction/Network/Policy
    learn.py                   LearnClient + learn 域 dataclass
    info.py                    InfoClient + info 域 dataclass
  services/                    应用编排层；依赖 sdk + config
    base.py                    BaseService + Listing[T] + CourseScopedListing[T]
                               + with_reauth + fanout_parallel
    auth.py                    AuthService（profile / login 用例 / status / logout）
    learn.py                   LearnService
    info.py                    InfoService
  config/                      路径 / profile / i18n
    profiles.py
    i18n.py
  cli/                         用户界面
    main.py                    入口 + 顶层 argparser
    shell.py                   交互式 REPL
    _common.py                 CommandContext + 自动发现
    output.py                  渲染 + JSON / 表格 / ui
    prompts.py                 终端 prompts + AuthInteraction 构造
    commands/
      auth/                    每个命令一个文件
      learn/
      info/
      campus/                  占位
      academic/                占位
```

**依赖方向**（架构 test 钉死）：

```
core   ← sdk   ← services   ← cli
                  ↑
                 config（被 services / cli 用）
```

- ❌ `core` 不得 import 任何上层
- ❌ `sdk` 不得 import `services` / `config` / `cli` ← 这是 "热插拔" 承诺的关键
- ❌ `services` 不得 import `cli`
- ❌ `config` 不得 import 任何高层

**命令文件协议**（架构 test 钉死）：

```python
# cli/commands/<domain>/<cmd>.py 必须 expose：
NAME: str
HELP: str
def register(subparsers): ...
def handle(args, ctx: CommandContext) -> int: ...
```

且**不得**直接构造 `AuthInteraction(...)` — 必须通过 `ctx.auth_kwargs()`。

---

<a id="extraction-guide"></a>
## Extraction Guide — 只想要部分功能

thu-cli 的 SDK 是按照 "外部应用只用部分功能" 设计的。下面是几种典型场景。

### 场景 A：只想 `pip install` 后导入

```bash
pip install thu-cli
```

```python
from thu_cli import LearnService, InfoService, AuthInteraction
```

完整的依赖管理，不用拷文件。

### 场景 B：师弟想拉成绩单，**复制粘贴到自己包里**

最小子集：把 `thu_cli/core/` + `thu_cli/sdk/` 两个目录拷到**自己的 package 路径**下（比如 `my_pkg/core/` + `my_pkg/sdk/`），改 import 前缀即可。

⚠️ **不要** 直接 `pip install thu-cli` 后只 `from thu_cli.sdk import ...` —— `thu_cli/__init__.py` 会主动 import `services/` + `config/`（顶层包是给最终用户的便利层）。要"轻量"只能拷贝代码，而不是装包后选择性 import。

架构保证 `sdk` 不会反向 import `services / config / cli`（由 `tests/test_architecture.py` 钉死），所以你拷过去后可以自由删 `services/` `config/` `cli/`。

```python
# my_script.py — 已把 thu_cli/core/ 和 thu_cli/sdk/ 拷成 my_pkg/core/ 和 my_pkg/sdk/
from pathlib import Path
from getpass import getpass

from my_pkg.sdk import SsoSession, InfoClient, AuthInteraction, Device
from my_pkg.core import WEBVPN_REALM, INFO_PORTAL, TRANSCRIPT_BKS

device = Device.load_or_create(Path("device.json"))
sso = SsoSession(device=device)
sso.username = "2023012168"
sso.ensure_realm(WEBVPN_REALM, interaction=AuthInteraction(passwd_fn=getpass))
sso.ensure_app(INFO_PORTAL, interaction=AuthInteraction(passwd_fn=getpass))
sso.ensure_app(TRANSCRIPT_BKS, interaction=AuthInteraction(passwd_fn=getpass))
sso.save(Path("session.json"))
print(InfoClient(sso).get_transcript_detail())
```

总成本：**2 个目录** ~12 个 .py 文件，零适配代码。

### 场景 C：想要自动重登 + warning 收集，但不要 CLI

加 `services/`：3 个目录 `core/` + `sdk/` + `services/`。`services/auth.py` 会引 `config/profiles`，所以也带上 `config/profiles.py` + `config/__init__.py` + `config/i18n.py`。

```python
from my_pkg import LearnService, AuthInteraction
service = LearnService()
listing = service.list_announcements(
    interaction=AuthInteraction(passwd_fn=...),
)
```

### 想确保自己抽出的子集独立可跑？

跑架构测试：

```bash
.venv/bin/pytest tests/test_architecture.py
```

会验证 `sdk → services/config/cli` 没有意外的 import 边。

---

## 扩展指南

### 加一个新 CampusApp

在 `core/apps.py` 添加：

```python
ELECTRICITY = CampusApp(
    id="electricity",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="<从 thu-info-app 抄>",
    parent_app=INFO_PORTAL,
    verify_url="",
)

CAMPUS_APPS["electricity"] = ELECTRICITY  # 加入注册表
```

### 加一个新命令

在 `cli/commands/<domain>/<cmd>.py` 写：

```python
from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "electricity"
HELP = "查询电费余额"


def register(subparsers):
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.set_defaults(_handler=handle)


def _render(result, ui):
    ui.section("电费")
    ui.kv([("余额", f"{result.balance:.2f}")])


register_renderer("campus_electricity", _render)


def handle(args, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    result = ctx.services.campus.get_electricity(user, **ctx.auth_kwargs(user))
    ctx.output.render(result, kind="campus_electricity")
    return 0
```

`cli/commands/campus/__init__.py` 的 `autodiscover_commands` 会自动发现并注册。

### 加一个新 service

在 `services/<domain>.py` 写：

```python
from .base import BaseService

class CampusService(BaseService):
    def get_electricity(self, user, *, interaction=None, network=None, policy=None):
        def call(force_login: bool):
            selected, sso = self.ensure_sso(
                user, realms=(WEBVPN_REALM,),
                interaction=interaction, network=network, policy=policy,
                force_login=force_login,
            )
            self.ensure_app_and_save(selected, sso, ELECTRICITY,
                                     interaction=interaction, policy=policy)
            return CampusClient(sso).get_electricity()
        return self.with_reauth(call)
```

`ctx.services` 也加一个字段把它挂上。

---

## 测试

```bash
.venv/bin/pytest -q                                  # 全套（不含 live）
.venv/bin/pytest tests/test_architecture.py          # 仅架构约束
THU_RUN_INTEGRATION=1 THU_USER=... THU_PASS=... \\
    .venv/bin/pytest tests/integration              # live（会触发 2FA）
```

开发常用检查：

```bash
.venv/bin/ruff check .
.venv/bin/python -m thu_cli --help
```

---

## 安全说明

- profile **不存密码**。密码靠 `AuthInteraction.passwd_fn` 回调按需提供
- 内存中密码只存在单次 process 生命周期内（`_cached_password`）
- `session.json` / `device.json` / `stage.json` 都以 0600 写入
- `--debug-dir` 会 dump 所有 HTTP 响应（含 set-cookie），仅 debug 用，**别提交**

---

## 已知 deprecation / 不计划做

| 功能 | 不做原因 |
|---|---|
| 教师 / TA 模式 | 用户群极小，写复杂度高 |
| 选课写操作（CR） | 极复杂、易争议 |
| 体育馆预约 | 复杂 write + 验证码 |
| 校园卡 / 电费充值 | 金钱 write，不承担风险 |
| 教评提交 | GUI 表单语义，非 agent 友好 |
| 邮件发送 | 用 SMTP 更标准 |
| GitLab | 用官方 git API 更标准 |
| 新闻订阅 | 用 RSS 更合适 |

---

## 许可证

本项目使用 MIT License，完整文本见 [LICENSE](LICENSE)。
