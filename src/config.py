import os
from dotenv import load_dotenv

load_dotenv(".env")

BOT_NAME="小贴"


# 聊天平台，可选'host'与'weixin'
CHAT_PLAT="host"

DATABASE_NAME='xiaotie'

LLM_TEXT_URL=os.getenv('LLM_TEXT_URL')
LLM_TEXT_NAME=os.getenv('LLM_TEXT_NAME')
LLM_TEXT_KEY=os.getenv('LLM_TEXT_KEY')

LLM_EMOTION_URL=os.getenv('LLM_EMOTION_URL')
LLM_EMOTION_NAME=os.getenv('LLM_EMOTION_NAME')
LLM_EMOTION_KEY=os.getenv('LLM_EMOTION_KEY')

LLM_IMAGE_URL=os.getenv('LLM_IMAGE_URL')
LLM_IMAGE_NAME=os.getenv('LLM_IMAGE_NAME')
LLM_IMAGE_KEY=os.getenv('LLM_IMAGE_KEY')


# 心情衰减率 兴趣衰减率
MOOD_DECAY_RATE=[0.95,0.9]
INTEREST_DECAY_RATE=[0.95,0.9]

MOOD_INFLUENCE_FACTOR=5  # 情感分析对心情值的影响因子

BUFFER_NUM = 10 # 缓冲池合并消息数的上限,超过则立即将消息送出队列


# ---------------- 疲惫值(疲劳/厌倦) ----------------
INTEREST_MAX = 100          # 兴趣值上限,mood.py 的 _clamp_values 里也是这个数
COMFORT_RATE = 0.3          # 舒适的消息密度(条/秒),
FATIGUE_GAIN = 0.06         # 超出舒适区时,每条消息带来的疲惫增量系数
FATIGUE_RECOVER_TAU = 180   # 被消息刷累的恢复时间常数(秒),安静时约 3 分钟消退 63%

# ---------------- 工作疲劳 ----------------
# 干活累和被消息刷累是**同一个方向**(都是不想干),所以对外合成一个疲惫值,
# 但内部分开记两笔账 —— 恢复速度不一样
WORK_COST_ROUND = 0.05      # 每圈思考(一次 LLM 调用)
WORK_COST_TOOL = 0.02       # 每次普通工具调用
WORK_COST_HEAVY = 0.08      # 每次重工具调用(slow=True,比如跑命令行、翻文件)
FATIGUE_WORK_TAU = 300      # 工作疲劳的恢复时间常数(秒),比被刷屏恢复得慢
DENSITY_MIN_SAMPLES = 3     # 估算密度所需的最少消息数,样本太少时不累(防冷启动)


# ---------------- 状态心跳 ----------------
STATE_TICK = 5              # 状态线程的 tick 间隔(秒)
                            # 各状态的衰减/恢复都用 exp(-Δt/τ),所以改这个值不会改变衰减曲线
REPLY_EAGERNESS_THRESHOLD = 0.5   # 发言意愿的参考线
                                  # 注意:现在它是**纯参考**,不拦截任何消息 ——
                                  # 回不回交给思考层自己判断(见 agent/think.py)。
                                  # 留着是为了将来想做硬下限时有个抓手。


# ---------------- 回复层 ----------------
REPLY_HISTORY_LIMIT = 20    # 说话层带多少条历史对话(直接影响提示词长度和成本)


# ---------------- 思考层 ----------------
# 安全上限,不是"疲劳的表达":她随时可以不返回 tool_calls 停下来自己答,
# 这里是防它卡在循环里。所以固定值就够了,不要拿它去映射状态
MAX_THINK_ROUNDS = 20       # 一轮思考最多几圈(一圈 = 一次 LLM 调用 + 若干次工具执行)
MAX_PENDING_TASKS = 3       # 同时在跑的后台任务上限,防止套娃把机器堆爆
THINK_HISTORY_LIMIT = 10    # 思考时带多少条历史对话进去
HISTORY_GAP_NOTICE = 1800   # 历史里两条消息隔得超过这个秒数就单独标一行(30 分钟)


# ---------------- 记忆网络 ----------------
MEMORY_SPREAD_DEPTH = 3     # 命中关键词后向外扩散几层(1 = 只取直接邻居)
RECALL_MAX_MEMORIES = 8     # 一次回忆最多塞几条进提示词(太多会冲淡当下的话题)
MEMORY_NODE_MAX_ITEMS = 30  # 单个节点最多存几条记忆,超出丢最旧的
MEMORY_BUFFER_TTL = 36000   # 候选关键词在 buffer 里等多久(秒),10 小时没被再提就放弃
MEMORY_EDGE_TTL = 360000    # 边的基础存活时长(秒),实际 = 它 × (log(权重)+1)


# ---------------- AI 的工作区 ----------------
# 只读:整个电脑都能看。 写/删:只能在这个目录里。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_WORKSPACE = os.getenv("WORKSPACE_PATH") or os.path.join(PROJECT_ROOT, "workspace_AI")


# ---------------- 文件操作 ----------------
FILE_READ_LIMIT = 8000      # 一次读回来多少字(超了用 offset 接着读)
FILE_WRITE_LIMIT = 200000   # 一次写多少字
FILE_LIST_LIMIT = 200       # 列目录最多几条

# 路径/命令里出现这些词就拒 —— 读出来会进 LLM 上下文,等于发给服务商。
# ⚠️ 这是**黑名单,天然会漏**:它挡的是"按名字一眼能看出的",不是"内容里有密钥的"。
# 尤其注意:即使挡掉了 .ssh 这种目录名,也挡不住别人给一个上层目录(比如 C:\Users\aaa)
CREDENTIAL_KEYWORDS = (
    ".env", "id_rsa", ".pem", ".key", "credential", "secret", "password", "apikey",
    ".ssh", ".aws", ".netrc", ".gnupg", ".npmrc", ".git-credentials",
)


# ---------------- 看图 ----------------
# 图片会被 base64 之后**整个塞进请求体**发给服务商,大小必须卡住 ——
# 一张 50MB 的图编码完 67MB,请求和上下文一起撑爆。
IMAGE_MAX_BYTES = 5 * 1024 * 1024   # 单张图上限
IMAGE_DESC_LIMIT = 1500             # 看完返回的文字留多少字
# 只认这些后缀。**不能只看 mime**:
#   .env 的 mime 是 None,会拼出 "data:None;base64,..."
#   .md  的 mime 是 text/markdown,拼出来还是个格式合法的 data URL,更容易混过去
# 后缀白名单是硬的,不看内容也不看声明。
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


# ---------------- 联网 ----------------
WEB_TIMEOUT = 15                    # 一次请求最多等多久(秒)
WEB_MAX_BYTES = 2 * 1024 * 1024     # 最多读多少字节(不信 Content-Length,它可撒谎)
WEB_TEXT_LIMIT = 6000               # 剥完标签的正文留多少字给她
WEB_MAX_REDIRECTS = 5               # 最多跟几次跳转(**每一跳都重查一遍内网**)
WEB_SEARCH_RESULTS = 8              # 搜索给她几条
# 搜索走必应的 **RSS** 形态 —— 返回 XML,不用去剥 HTML。
# ⚠️ 必须 cn.bing.com:www.bing.com 会走代理节点,中文结果被污染
# （同一个"极光",www 版第一条是"如何评价GPT-6…"）。
WEB_SEARCH_ENDPOINT = "https://cn.bing.com/search"


# ---------------- 命令行工具 ----------------
COMMAND_TIMEOUT = 10        # 单条命令的超时(秒)
COMMAND_MAX_TIMEOUT = 30    # 模型自己传 timeout 时的上限
COMMAND_OUTPUT_LIMIT = 2000 # 输出截断长度,防止一条命令把上下文撑满


# ---------------- 外包给别的 agent ----------------
# 重活(翻几十个文件、跑很多轮)扔给独立的 agent 进程,免得占死她的消息队列
AGENT_COMMAND = "claude"        # 用哪个 agent,要能在 PATH 里找到
AGENT_TIMEOUT = 300             # 一次外包最多跑多久(秒),超了直接掐
AGENT_RESULT_LIMIT = 3000       # 结果给她多少字,剩下的留在工作台里让她自己读
AGENT_THINK_NOTICE = 800        # 窗口里"正在想"每涨这么多 token 报一次
AGENT_WORKBENCH = "_workbench"  # 工作台目录名(在 AI_WORKSPACE 下)
# 在自己工作台干活时额外放行的命令。
# ⚠️ 放行 python = 放行任意代码执行 —— 代码里的路径没法检查,
# 所以它理论上能写到工作区外、能读密钥文件。这一条是**信任**,不是防线。
# 换来的好处:写出来的脚本能立刻验证,不然只能写不能跑。
# 另外注意:**只读模式(给了 look_at)下不会带上这个** ——
# "能读全盘" 和 "能执行代码" 永远不同时出现。
AGENT_ALLOWED_TOOLS = "Bash(python *)"


# ---------------- 跑脚本 ----------------
SCRIPT_TIMEOUT = 30         # 她自己写在工作区里的脚本最多跑多久(秒)
# 子进程不要看到密钥类的环境变量,否则一个 print(os.environ) 就漏了
ENV_SECRET_PARTS = ("key", "token", "secret", "password", "credential", "auth")


# ---------------- 自发循环 ----------------
BOREDOM_RISE_TAU = 900      # 无聊涨到 63% 要多久(秒),15 分钟
IDLE_BOREDOM_THRESHOLD = 0.65  # 无聊到这个程度才考虑自己找事做
IDLE_MIN_SILENCE = 180      # 至少安静这么久(秒)才不打扰 —— 免得刚说完就自己接话
IDLE_COOLDOWN = 600         # 自己动过一次之后至少隔这么久(秒)再来
IDLE_SATISFY = 0.5          # 每次忙起来能消掉多少无聊
IDLE_TICK = 30              # 自发循环多久看一次(秒)
IDLE_FATIGUE_LIMIT = 0.7    # 累到这个程度就别自己找事了