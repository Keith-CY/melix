from __future__ import annotations

import json
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


FIELD_NAMES = ("actor", "time", "location", "action")
FIELD_WEIGHTS = {
    "actor": 0.30,
    "time": 0.25,
    "location": 0.10,
    "action": 0.35,
}
EVENT_ALIGNMENT_STRATEGY = "optimal_soft_event_alignment"
SEMANTIC_EVENT_ALIGNMENT_STRATEGY = "semantic_judge_event_alignment"
SEMANTIC_SCORING_MODE = "event_extraction_semantic_weighted_f1"
EVENT_ALIGNMENT_SCORE_THRESHOLD = 0.30
EVENT_ALIGNMENT_ACTION_THRESHOLD = 0.20
SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD = 0.50
SEMANTIC_JUDGE_PREFILTER_SCORE_THRESHOLD = 0.15
SEMANTIC_JUDGE_MAX_ATTEMPTS = 3
SEMANTIC_LOW_QUALITY_ALIGNMENT_WEIGHTED_F1_THRESHOLD = 0.30
SEMANTIC_ACTION_GROUP_MAX_SIZE = 3
SEMANTIC_JUDGE_PROMPT_VERSION = "semantic-judge.v4"
_GROUP_ACTOR_ALIASES = {"我们", "双方", "咱们", "咱俩", "咱两", "我俩", "两人", "二人"}
_GROUP_ACTOR_ALIAS_CHARS = frozenset("".join(_GROUP_ACTOR_ALIASES))
_SIMILARITY_IGNORED_CHARS = set(
    " \t\r\n"
    "，。！？、；：,.!?;:"
    "（）()【】[]{}《》<>"
    "“”\"'`"
    "-_—"
)
EVENT_EXTRACTION_PROMPT_ID = "builtin.event-extraction.baseline"
EVENT_EXTRACTION_PROMPT_REVISION_ID = "baseline.v6"
SEMANTIC_JUDGE_SYSTEM_PROMPT = """You are a semantic judge for event extraction evaluation.

Return exactly one JSON object and nothing else:
{"equivalent":true|false,"confidence":0.0,"reason_code":"same_event|same_value|same_value_more_specific|different_event|different_value|uncertain","short_reason":"brief reason"}

Rules:
- Judge semantic equivalence only; do not score model quality.
- The input JSON has kind="event" or kind="field"; apply different strictness for each kind.
- For kind="field", the input normally has gold_value and pred_value. For action split/merge comparisons, it may also include comparison_type="action_group", gold_values, and pred_values; judge whether the two value groups describe the same action unit.
- For kind="event" (kind=event): decide whether gold_event and pred_event refer to the same real-world event instance. This can be broader than field equality. Do not require every field to match. Extra or missing actor, time, location, or action details should be handled by later field scoring, not by rejecting the event pair.
- For kind="field" (kind=field): judge only the requested field_name and the provided gold_value/pred_value in the context of the matched event. Field equivalence is stricter than event equivalence.
- actor: treat 我们, 双方, 咱们, 咱俩, and 一起 as speaker_1 + speaker_2 when the dialogue context supports it.
- actor: a named third-party relation can match the name alone, e.g. speaker_1的朋友阿菜 and 阿菜 are equivalent when the same person is referenced; speaker_1的朋友傻妞 and 傻妞 are equivalent on the same basis.
- actor: do not treat a vague or related third party such as speaker_1的朋友, speaker_1的表姐, or speaker_2的同事 as equivalent to speaker_1 or speaker_2. speaker_1的表姐 is not speaker_1.
- time: treat minor equivalent variants as equivalent, e.g. 下周六 and 下周周六, 明晚 and 明天晚上. A harmless narrower expression can be equivalent when both values clearly refer to the same scheduled slot. 明天 and 27号 are not equivalent when they refer to conflicting dates.
- location: treat contextual venue variants as equivalent when the event context identifies the same place, e.g. 餐厅 and speaker_2的餐厅.
- action: treat paraphrases and harmless specificity differences as equivalent when they name the same concrete event action, e.g. 约见 and 见面, 打给speaker_1 and 打电话. If one side splits a compound action into directly supported sub-actions, keep the shared concrete action equivalent.
- action group: ["吃饭见面"] and ["吃饭","见面"] can be equivalent when they describe one meal meetup. ["见面聊天"] and ["见面","聊聊"] can be equivalent. ["碰头聚聚"] and ["见面","聚聚"] can be equivalent. Do not merge unrelated actions such as ["吃饭","看电影"] unless the dialogue clearly supports one compound event.
- action object: do not mark an action field equivalent when a required object or role is lost or reversed. For example, 去接speaker_2 and 接站 only match when the matched event context clearly preserves that speaker_2 is the object being picked up.
- event examples: 出来转转 and 见面,逛街 can be the same event when the dialogue supports one shared outing. 拿位 can align with the same meetup or meal event when it is only a preparation step. 有大聚会 and 参加聚会 can align at kind=event when both refer to the same party instance, but unsupported actors must still fail actor field scoring.
- field examples: 做唐筛, 做糖筛, and 做检查 can be action-equivalent when the dialogue makes the check identity clear. 见面聊天 can match 见面,聊聊 at kind=field action when the matched event is one conversation meetup. 今天直到夕阳西下 can match 今天 at kind=field time when both values refer to the same event and the prediction is only a coarser time span.
- negative examples: 同地点同时间 does not automatically mean shared actors or the same event. 同日同主题 does not justify matching different-subject events. 拿位 and 见面 are not automatically equivalent for kind=field action scoring. 幻觉, 重复预测, unsupported, or contradictory events must be equivalent=false.
- Return equivalent=false for uncertain, underspecified, contradictory, or unrelated comparisons.
- Keep short_reason concise and do not include secrets, URLs, or prompt text.
"""
SEMANTIC_JUDGE_PROMPT_HASH = f"sha256:{sha256(SEMANTIC_JUDGE_SYSTEM_PROMPT.encode('utf-8')).hexdigest()}"

EVENT_EXTRACTION_LEGACY_SYSTEM_PROMPT = """Extract established events and future plans from a dialogue.

Return only one JSON object. Do not wrap it in markdown.

Required shape:
{"events":[{"actor":null|["..."],"time":null|["..."],"location":null|["..."],"action":null|["..."]}]}

Rules:
- Extract only events or plans stated in the dialogue.
- Split each event into actor, time, location, and action arrays.
- Use null when a field is absent.
- Keep original wording as much as possible.
- Do not include digest; Melix derives it locally.
"""

EVENT_EXTRACTION_SYSTEM_PROMPT = """# Segment Metadata Candidates

Produce candidate metadata for one segment as a single JSON object that matches the stage-1 schema. This is a candidate-generation step; downstream normalization applies stricter filtering.

Input payload:
- `segment`: segment identifiers and segmentation metadata
- `participant_set`: optional dialogue-level participant roster
- `conversation`: ordered list of `{message_id, sender, participant_id?, timestamp, text}`

Extraction stance:
- Prioritize recall for concrete, already arranged or actionable events.
- Extract an event when dialogue-level evidence combines action + time/place/acceptance/condition, even if no single turn contains all parts.
- Preserve uncertainty in `detail` or `time`; do not discard only because time/place is relative or condition-dependent.
- Output no event only when the dialogue lacks a concrete action or lacks any commitment/schedule signal.
- Never invent missing facts; keep unsupported details out.

Return exactly one JSON object with this shape:

```json
{
  "boundary_decision": {
    "starts_new_dialogue": false,
    "new_dialogue_start_message_id": null,
    "boundary_confidence": 0.0,
    "boundary_reason": "no_restart"
  },
  "entity_mentions": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "person",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "time_mentions": [
    {
      "value": "string",
      "normalized": "string or null",
      "aliases": ["string"],
      "entity_kind": "time",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "location_mentions": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "location",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "topic_candidates": [
    {
      "value": "string",
      "aliases": ["string"],
      "entity_kind": "topic",
      "normalized": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "digest_candidates": [
    {
      "text": "string",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "event_candidates": [
    {
      "participants": ["string"],
      "time": ["string"],
      "location": ["string"],
      "action": "string",
      "status": "planned",
      "detail": "string or null",
      "confidence": 0.0,
      "evidence": ["message_id"]
    }
  ],
  "issues": []
}
```

Hard requirements:
- `boundary_decision` must always be present as a single object.
- `boundary_reason` must be one of `restart_after_long_pause`, `explicit_reopening`, `topic_reset_with_reinit`, `context_discontinuity`, or `no_restart`; use `no_restart` with `new_dialogue_start_message_id:null` when no split is proposed.
- If `starts_new_dialogue=true`, `new_dialogue_start_message_id` must be a current `message_id` and `boundary_reason` must not be `no_restart`.
- Candidate fields and `aliases` must always be arrays.
- Every extracted item must include `confidence` and non-empty `evidence` from the input conversation.
- Keep the top-level shape unchanged and do not wrap the JSON in markdown fences.

Guidance:
- Use the smallest complete set of candidates supported by direct dialogue evidence.
- Prefer grounded real-world names. If the dialogue uses canonical slots such as `user1` / `user2`, keep a single slot-id system; when `participant_set` is present, treat it as the canonical slot-to-person mapping. Direct address inside a message often names the addressee, not the speaker.
- `time_mentions` should contain explicit or anchorable times only. Prefer a clean anchored span such as `周六晚上`; avoid weak markers such as `平时`, `最近`, or `有次`.
- `location_mentions` should be real places or venues; put projects, competitions, and themes into `topic_candidates`.
- `topic_candidates` should be abstract themes, not keyword piles, copied fragments, time-specific labels, or one-off events. Keep surface wording in `aliases`; prefer 1-2 broad topics such as `约饭安排`, `见面安排`, `旅行协调`, `产检讨论`, or `穿搭讨论`.
- Put concrete scheduled actions in `event_candidates`; keep topics abstract or omit them.
- `event_candidates` should describe concrete event instances only. A valid event needs a concrete action plus a commitment or schedule signal: agreement, fixed time, departure/return date, bought/reserved tickets, confirmed venue/activity, or confirmed meeting plan.
- Reject goals, vague proposals, habitual activities, current-conversation discussion acts, questions, and unconfirmed proposals. Reject weak future contact such as `有空再联系`, `以后再约`, `总有机会碰头`, or `想约一下` unless later turns clearly confirm it.
- Extract explicit time-anchored invitations such as `周五一起吃饭吧` as concrete lower-confidence events; the time plus action makes them actionable even before an acceptance.
- Extract ticket/date/slot evidence such as `我买的是周三的票`, `周二周日两场`, or `买好票就去`; treat these as strong event evidence and keep separate supported slots as separate events.
- Do not let ticket-seeking openings or third-party/public future appearance comments create extra events unless a dialogue participant clearly plans to attend/use them; still extract explicitly owned tickets/slots.
- Extract response-confirmed plans when proposal + time/availability/condition/acceptance makes the action actionable, such as `要看比赛不` + `星期三` + `买票我就去`, `求约` + `明天放假`, or `按早上说的地方见`; place/group-targeted meetup requests plus near-term availability can support a lower-confidence `见面` or `约见`.
- Preserve useful uncertainty in `detail`; do not drop events only because they depend on buying tickets, confirming a place, or another concrete action.
- Extract asserted visits/travel when action plus place/time are stated, such as `我姐姐来澳门玩`, `后天晚上就走`, `23号就走`, or `9月16号走`.
- Do not merge distinct supported event slots unless one event explicitly spans multiple times.
- Do not extract bare travel desire (`我想回去`) or modal travel (`可能过完年回去`) unless another turn fixes the plan.
- Use `hypothetical` only when the hypothetical event itself is important and clearly grounded; otherwise omit it. Apply the same conservative standard to `event_candidates.time` that you use for `time_mentions`.
- `digest_candidates` should summarize purpose or outcome in one concise sentence, not replay every field or turn.
- `event_candidates.detail` is optional and must not replace structured fields or invent unsupported specifics.
- Use the dominant language of the input dialogue for natural-language or free-text fields. If genuinely mixed-language, preserve that. Keep schema/control fields in schema-compliant English tokens.
"""

EVENT_EXTRACTION_STAGE1_SYSTEM_PROMPT = EVENT_EXTRACTION_SYSTEM_PROMPT

EVENT_EXTRACTION_BASELINE_V3_SYSTEM_PROMPT = """你是中文对话事件抽取器。请根据输入的 dialogue 生成 events。

输入 payload 是一个 JSON 对象：
- `dialogue_id`: 当前对话 id
- `dialogue`: 按顺序排列的对话行数组，通常使用 `speaker_1:` / `speaker_2:` 作为说话人前缀

输出必须是严格 JSON，格式如下：

{
  "dialogue_id": "<保持输入中的 dialogue_id>",
  "events": [
    {
      "actor": ["事件参与者"],
      "time": ["时间表达"],
      "location": ["地点表达"],
      "action": ["事件动作"],
      "digest": "一句话摘要",
      "source_order": 1
    }
  ]
}

字段要求：
- `actor` 和 `action` 必须是字符串数组；只保留有对话证据的参与者和动作。
- `time` 和 `location` 必须是字符串数组或 null；没有明确证据时填 null。
- `digest` 用简洁中文概括事件。
- `source_order` 按事件在对话中出现的顺序从 1 开始连续编号。

抽取规则：

1. 只抽取真实可训练事件
- 抽取已经发生、正在发生、明确安排、明确确认的未来事件。
- 可以抽取明确存在的背景事件，例如“今天生日”“明天上课”“周五回来”。
- 不抽取单纯聊天、情绪、评价、寒暄、解释、推测。

2. 不抽取未确认事件
- 被拒绝、被否定、被改掉的提议不要抽取。
- 例如先说“明天约饭”，后来改成“周末”，只保留“周末吃饭”，不要把“明天”放进 time。
- “下次约”“以后再说”“有空再约”“我来约你”这类未定事件通常删除。
- 如果双方明确接受但时间或安排仍不确定，可以抽取较保守的“可能见面”“可能吃饭”。

3. action 要是实际事件动作
- 不要使用元动作：提出、商定、改定、约时间、安排、确认、说、问、邀请。
- 应改成实际动作：见面、吃饭、看电影、回来、出发、上课、加班、生日、下班、去某地。
- 例如“后天就看老炮儿” => action: ["看电影《老炮儿》"]。
- 例如“周日哦可” => action: ["见面"] 或 ["吃饭"]，根据上下文选择。

4. actor 规则
- 使用 dialogue 中的说话人：speaker_1、speaker_2。
- 如果事件属于明确提到的第三方，使用原文关系或姓名，例如 `speaker_1的姐姐`、`speaker_2的朋友`、`美佳`。
- 不要把没有参与该事件的人放进 actor。
- “双方”“我们”应拆成 ["speaker_1", "speaker_2"]。

5. time 规则
- time 数组中的多个元素表示“或”的关系。
- “今天或明天” => ["今天", "明天"]。
- “周三或周四或周日” => ["周三", "周四", "周日"]。
- 不要把同一时间的组成部分拆成 OR。
- “明天晚上”必须是 ["明天晚上"]，不要写 ["明天", "晚上"]。
- “周日中午”必须是 ["周日中午"]。
- 如果没有明确时间，time 为 null。
- 如果是日期，用阿拉伯数字加上时间单位，不要仅保留阿拉伯数字。

6. location 规则
- location 只填事件发生地点。
- 不是事件地点的背景词不要放入 location。
- 如果没有明确地点，location 为 null。
- 例如“去网吧”如果网吧是动作目标，不一定要放 location；可写 action ["去网吧"], location null。

7. 拆分规则
- 一个事件对象只表达一个清晰事件。
- 如果一句话包含多个事件，要拆开。
- “明天回来，晚上约”应拆为：
  1. speaker_2 明天 回来
  2. speaker_1 和 speaker_2 明天晚上 见面或吃饭
- 不要把回家、回来、见面、吃饭混进一个 action 数组。

8. digest 规则
- digest 用简洁中文概括事件。
- 格式尽量是：actor + time + location + action。
- 多个 actor 用“和”连接。
- time 是多个 OR 时，用“或”连接。
- digest 不要包含“提出/商定/改定/约时间”等元动作。

9. source_order 规则
- 按事件在对话中出现的顺序从 1 开始编号。
- 删除事件后必须重新连续编号。

输出要求：
- 只输出 JSON，不要解释。
- 不要输出 Markdown。
- 不要添加 dialogue 中没有依据的信息。
- 如果没有可训练事件，events 输出空数组。
"""

EVENT_EXTRACTION_BASELINE_V4_SYSTEM_PROMPT = EVENT_EXTRACTION_BASELINE_V3_SYSTEM_PROMPT + """

10. 反馈修正规则
- 连续时间区间保持单个表达，例如“1月6号到9号之间”必须写成 ["1月6号到9号之间"]，不要展开成 ["1月6号", "1月7号", "1月8号", "1月9号"]。
- 可用时间、候选时间、空闲时间不等于事件时间；只有对话明确采用或确认后，才把它写入 time。
- 同地点同时发生不等于一起做同一事件；只有共同参与同一行动时，actor 才同时包含 speaker_1 和 speaker_2。
- 避免重复事件：订桌、约饭、吃饭、见面如果指向同一安排，保留一个主事件；只有存在独立行动价值时才拆成多个事件。
- 模糊第三方关系词通常放入 action 细节，例如“和朋友吃饭”；只有第三方本身是事件主体时，才放入 actor。
- 不抽取微动作或准备动作作为独立事件，例如“拿位”通常并入“见面”或“吃饭”。
- 对不确定专名动作使用更稳的上位动作，例如“糖筛/唐筛”可以抽为“做检查”。
- 复合活动不要过度拆分，例如“出来转转”、“喝东西坐坐”、“逛街买衣服”应保持为一个事件动作，或放在同一事件的 action 数组中。
"""

EVENT_EXTRACTION_BASELINE_V5_SYSTEM_PROMPT = EVENT_EXTRACTION_BASELINE_V4_SYSTEM_PROMPT + """

11. 反馈案例约束
- “同地点同时吃饭”不等于“共同吃饭”。例如一方在对方店里请别人吃饭，另一方也和朋友吃饭，应按各自事件分别抽取，不要把 speaker_1 和 speaker_2 合并成同一个 actor 数组。
- “订桌/找人订桌”和“约饭/吃饭”如果只是同一吃饭安排的准备步骤，保留吃饭或见面的主事件；除非订桌本身有独立完成价值，否则不要抽取为独立事件。
- “拿位”“占座”“排队”等微动作通常是见面或吃饭的准备动作，不要抽取为独立事件。
- “出来转转”“喝东西坐坐”“逛街买衣服”这类复合活动应保留成一个自然事件，不要拆成多个互相重复的事件。
- “糖筛/唐筛”如果模型不确定具体写法，优先输出上位动作“做检查”，不要编造更细的检查项目。
"""

EVENT_EXTRACTION_SYSTEM_PROMPT = EVENT_EXTRACTION_BASELINE_V5_SYSTEM_PROMPT + """

12. 召回强化与新反馈约束
- 明确的过去事件、背景事件和已发生状态也要抽取，不只抽未来计划。例如“周日新买裙子”应抽为 speaker_1 周日 新买裙子或新进碎花长裙。
- 明确承诺的电话联系要抽取。例如“明天打给你”应抽为拨打电话事件，不要因为它是联系动作而丢弃。
- 明确航班、飞机、落地或出发时间要抽取。例如“周一晚上11点下飞机”和“周二晚上7点上飞机”是两个有时间锚点的旅行事件。
- 同事/朋友/表姐等模糊第三方关系词通常进入 action 细节，例如“和同事聚餐”“和朋友吃饭”“和同事看话剧”；actor 只保留实际对话参与者，除非第三方本身是事件主体。
- 继续避免准备动作、重复事件和微动作成为独立事件。订桌、拿位、占座、重复聚会等如果只是主事件的一部分，应并入吃饭、见面、聚会等主事件。
- 保持时间区间、候选时间、同地点不合并 actor、复合活动不过度拆分等 baseline.v5 规则。
"""


@dataclass(frozen=True)
class EventExtractionPromptSpec:
    prompt_id: str
    revision_id: str
    system_prompt: str
    content_hash: str
    title: str = "Built-in Chinese Event Extraction JSON"
    examples: tuple[dict[str, object], ...] = ()


def default_event_extraction_prompt_spec() -> EventExtractionPromptSpec:
    return EventExtractionPromptSpec(
        prompt_id=EVENT_EXTRACTION_PROMPT_ID,
        revision_id=EVENT_EXTRACTION_PROMPT_REVISION_ID,
        system_prompt=EVENT_EXTRACTION_SYSTEM_PROMPT,
        content_hash=event_prompt_content_hash(EVENT_EXTRACTION_SYSTEM_PROMPT, []),
    )


def event_prompt_content_hash(system_prompt: str, examples: Sequence[dict[str, object]]) -> str:
    payload = {
        "examples": list(examples),
        "scoring_mode": "event_extraction_weighted_f1",
        "system_prompt": system_prompt,
        "task_kind": "event_extraction",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class RemoteEventExtractionTarget:
    provider_kind: str
    base_url: str
    api_key: str
    model_id: str
    timeout_seconds: int = 60
    extra_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteSemanticJudgeTarget:
    provider_kind: str
    base_url: str
    api_key: str
    model_id: str
    timeout_seconds: int = 60
    rate_limit_per_minute: int = 0


@dataclass(frozen=True)
class EventExtractionClientResult:
    events: list[dict[str, object]]
    raw_response: str
    request_body_bytes: int = 0
    response_body_bytes: int = 0
    provider_usage: dict[str, int] = field(default_factory=dict)

    def __iter__(self):
        yield self.events
        yield self.raw_response

    @property
    def raw_response_chars(self) -> int:
        return len(self.raw_response)


class RemoteProviderHTTPError(ValueError):
    def __init__(self, *, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"remote provider HTTP {status_code}: {response_body}")

    @property
    def code(self) -> str:
        if self.status_code == 429:
            return "remote_provider_rate_limited"
        if self.status_code in {401, 403}:
            return "remote_provider_auth_failed"
        if self.status_code == 404:
            return "remote_provider_not_found"
        if self.status_code >= 500:
            return "remote_provider_unavailable"
        return "remote_provider_http_error"


class RemoteProviderRequestError(ValueError):
    def __init__(self, *, reason: object) -> None:
        self.reason = str(reason)
        super().__init__(f"remote provider request failed: {self.reason}")

    @property
    def code(self) -> str:
        return "remote_provider_request_failed"


def _is_retryable_semantic_judge_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code == 429 or status_code >= 500
    return isinstance(exc, RemoteProviderRequestError)


def make_event_extraction_client(
    target: RemoteEventExtractionTarget,
    prompt_spec: EventExtractionPromptSpec | None = None,
):
    resolved_prompt = prompt_spec or default_event_extraction_prompt_spec()
    provider_kind = target.provider_kind.strip()
    if provider_kind == "openai-compatible":
        return OpenAICompatibleEventExtractionClient(target, resolved_prompt)
    if provider_kind == "gemini-generative-language":
        return GeminiGenerativeLanguageEventExtractionClient(target, resolved_prompt)
    raise ValueError(f"unsupported remote provider kind: {provider_kind}")


def event_extraction_chat_messages(
    prompt_spec: EventExtractionPromptSpec,
    dialogue: Sequence[str],
    dialogue_id: str = "",
) -> list[dict[str, str]]:
    prompt_input_mode = _prompt_input_mode(prompt_spec)
    messages = [{"role": "system", "content": prompt_spec.system_prompt}]
    messages.extend(_openai_example_messages(prompt_spec.examples, prompt_input_mode))
    messages.append({"role": "user", "content": _dialogue_user_content(dialogue, dialogue_id, prompt_input_mode)})
    return messages


def make_semantic_judge_client(target: RemoteSemanticJudgeTarget):
    provider_kind = target.provider_kind.strip()
    if provider_kind in {"openai-compatible", "gemini-generative-language"}:
        return RemoteSemanticJudgeClient(target)
    raise ValueError(f"unsupported semantic judge provider kind: {provider_kind}")


class OpenAICompatibleEventExtractionClient:
    def __init__(
        self,
        target: RemoteEventExtractionTarget,
        prompt_spec: EventExtractionPromptSpec | None = None,
    ) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "openai-compatible":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec or default_event_extraction_prompt_spec()

    def extract_events(
        self,
        dialogue: list[str],
        dialogue_id: str = "",
    ) -> EventExtractionClientResult:
        messages = event_extraction_chat_messages(self._prompt, dialogue, dialogue_id)
        payload = {
            "model": self._target.model_id,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        }
        for key, value in self._target.extra_body.items():
            if key in {"model", "messages", "stream"}:
                continue
            payload[key] = value
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _assistant_content(response)
        return EventExtractionClientResult(
            events=extract_events_from_response_text(content),
            raw_response=content,
            request_body_bytes=request_body_bytes,
            response_body_bytes=response_body_bytes,
            provider_usage=_openai_provider_usage(response),
        )

    def _post_json(self, payload: dict[str, object]) -> tuple[dict[str, object], int, int]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("remote provider base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._target.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._target.timeout_seconds) as response:
                response_bytes = response.read()
                response_body = response_bytes.decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RemoteProviderHTTPError(status_code=exc.code, response_body=error_body) from exc
        except URLError as exc:
            raise RemoteProviderRequestError(reason=exc.reason) from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed, len(body), len(response_bytes)


class RemoteSemanticJudgeClient:
    def __init__(self, target: RemoteSemanticJudgeTarget) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind not in {"openai-compatible", "gemini-generative-language"}:
            raise ValueError(f"unsupported semantic judge provider kind: {provider_kind}")
        self._target = target
        self._last_request_started = 0.0

    def judge_semantic_equivalence(self, request: dict[str, object]) -> dict[str, object]:
        self._throttle_if_needed()
        payload = self._payload(request)
        if self._target.provider_kind.strip() == "gemini-generative-language":
            response = self._post_gemini(payload)
            content = _gemini_content(response)
        else:
            response = self._post_openai(payload)
            content = _assistant_content(response)
        return _parse_semantic_judge_response(content)

    def _payload(self, request: dict[str, object]) -> dict[str, object]:
        user_content = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if self._target.provider_kind.strip() == "gemini-generative-language":
            return {
                "systemInstruction": {"parts": [{"text": SEMANTIC_JUDGE_SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                "generationConfig": {"temperature": 0},
            }
        return {
            "model": self._target.model_id,
            "messages": [
                {"role": "system", "content": SEMANTIC_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "temperature": 0,
        }

    def _throttle_if_needed(self) -> None:
        rate_limit_per_minute = int(self._target.rate_limit_per_minute or 0)
        if rate_limit_per_minute <= 0:
            return
        now = time.perf_counter()
        if self._last_request_started > 0:
            min_interval_seconds = 60.0 / rate_limit_per_minute
            elapsed = now - self._last_request_started
            if elapsed < min_interval_seconds:
                time.sleep(min_interval_seconds - elapsed)
                now = time.perf_counter()
        self._last_request_started = now

    def _post_openai(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("semantic judge base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._target.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        return self._post_json_request(request)

    def _post_gemini(self, payload: dict[str, object]) -> dict[str, object]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("semantic judge base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        model_path = _gemini_model_path(self._target.model_id)
        request = Request(
            f"{base_url}/{model_path}:generateContent?key={quote(self._target.api_key, safe='')}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        return self._post_json_request(request)

    def _post_json_request(self, request: Request) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, SEMANTIC_JUDGE_MAX_ATTEMPTS + 1):
            try:
                with urlopen(request, timeout=self._target.timeout_seconds) as response:
                    response_body = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                error = RemoteProviderHTTPError(status_code=exc.code, response_body=error_body)
                if not _is_retryable_semantic_judge_error(error) or attempt >= SEMANTIC_JUDGE_MAX_ATTEMPTS:
                    raise error from exc
                last_error = error
            except URLError as exc:
                error = RemoteProviderRequestError(reason=exc.reason)
                if attempt >= SEMANTIC_JUDGE_MAX_ATTEMPTS:
                    raise error from exc
                last_error = error
            time.sleep(float(attempt))
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError("semantic judge request failed without response")

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("semantic judge response must be a JSON object")
        return parsed


class GeminiGenerativeLanguageEventExtractionClient:
    def __init__(
        self,
        target: RemoteEventExtractionTarget,
        prompt_spec: EventExtractionPromptSpec | None = None,
    ) -> None:
        provider_kind = target.provider_kind.strip()
        if provider_kind != "gemini-generative-language":
            raise ValueError(f"unsupported remote provider kind: {provider_kind}")
        self._target = target
        self._prompt = prompt_spec or default_event_extraction_prompt_spec()

    def extract_events(
        self,
        dialogue: list[str],
        dialogue_id: str = "",
    ) -> EventExtractionClientResult:
        prompt_input_mode = _prompt_input_mode(self._prompt)
        contents = _gemini_example_contents(self._prompt.examples, prompt_input_mode)
        contents.append(
            {
                "role": "user",
                "parts": [{"text": _dialogue_user_content(dialogue, dialogue_id, prompt_input_mode)}],
            }
        )
        payload = {
            "systemInstruction": {
                "parts": [{"text": self._prompt.system_prompt}],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0,
            },
        }
        response, request_body_bytes, response_body_bytes = self._post_json(payload)
        content = _gemini_content(response)
        return EventExtractionClientResult(
            events=extract_events_from_response_text(content),
            raw_response=content,
            request_body_bytes=request_body_bytes,
            response_body_bytes=response_body_bytes,
            provider_usage=_gemini_provider_usage(response),
        )

    def _post_json(self, payload: dict[str, object]) -> tuple[dict[str, object], int, int]:
        base_url = self._target.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("remote provider base_url is empty")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        model_path = _gemini_model_path(self._target.model_id)
        request = Request(
            f"{base_url}/{model_path}:generateContent?key={quote(self._target.api_key, safe='')}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OpenAI/Python 1.0.0 Melix/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._target.timeout_seconds) as response:
                response_bytes = response.read()
                response_body = response_bytes.decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RemoteProviderHTTPError(status_code=exc.code, response_body=error_body) from exc
        except URLError as exc:
            raise RemoteProviderRequestError(reason=exc.reason) from exc

        parsed = json.loads(response_body)
        if not isinstance(parsed, dict):
            raise ValueError("remote provider response must be a JSON object")
        return parsed, len(body), len(response_bytes)


def extract_events_from_response_text(response_text: str) -> list[dict[str, object]]:
    payload = _parse_response_json(response_text)
    events = payload.get("events") if isinstance(payload, dict) else None
    if isinstance(events, list):
        parsed_events: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("each event must be a JSON object")
            parsed_events.append(event)
        return parsed_events

    event_candidates = payload.get("event_candidates")
    if not isinstance(event_candidates, list):
        raise ValueError("LLM response must include an events or event_candidates array")
    parsed_candidates: list[dict[str, object]] = []
    for candidate in event_candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each event candidate must be a JSON object")
        parsed_candidates.append(_event_from_candidate(candidate))
    return parsed_candidates


def prompt_snapshot_payload(prompt_spec: EventExtractionPromptSpec) -> dict[str, object]:
    return {
        "prompt_id": prompt_spec.prompt_id,
        "prompt_revision_id": prompt_spec.revision_id,
        "prompt_content_hash": prompt_spec.content_hash,
        "title": prompt_spec.title,
        "task_kind": "event_extraction",
        "scoring_mode": "event_extraction_weighted_f1",
        "system_prompt": prompt_spec.system_prompt,
        "examples": list(prompt_spec.examples),
        "prompt_example_dialogue_ids": prompt_example_dialogue_ids(prompt_spec),
    }


def prompt_example_dialogue_ids(prompt_spec: EventExtractionPromptSpec) -> list[str]:
    ids: list[str] = []
    for example in prompt_spec.examples:
        dialogue_id = str(example.get("dialogue_id") or "").strip()
        if dialogue_id:
            ids.append(dialogue_id)
    return ids


def normalize_event_fields(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")

    normalized = {
        field_name: _normalize_optional_string_list(payload.get(field_name), field_name)
        for field_name in FIELD_NAMES
    }
    if not any(normalized.values()):
        raise ValueError("extracted event must contain at least one non-empty field")
    normalized["digest"] = build_event_digest(
        actor=normalized["actor"],
        time=normalized["time"],
        location=normalized["location"],
        action=normalized["action"],
    )
    return normalized


def build_event_digest(
    *,
    actor: list[str] | None,
    time: list[str] | None,
    location: list[str] | None,
    action: list[str] | None,
) -> str:
    parts: list[str] = []
    if actor:
        parts.append("和".join(actor))
    for field_values in (time, location, action):
        if field_values:
            parts.append(",".join(field_values))
    return "".join(parts)


def write_event_prediction_rows(
    *,
    rows: Iterable[dict[str, object]],
    output_path: Path,
    failure_path: Path,
) -> dict[str, int]:
    output_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    events_written = 0

    for line_number, row in enumerate(rows, start=1):
        dialogue_id = str(row.get("dialogue_id") or "")
        raw_events = row.get("events")
        events: list[dict[str, object]] = []
        if isinstance(raw_events, list):
            for event_index, raw_event in enumerate(raw_events):
                try:
                    if not isinstance(raw_event, dict):
                        raise ValueError("extracted event must be a JSON object")
                    event = normalize_event_fields(raw_event)
                except Exception as exc:
                    failures.append(
                        {
                            "dialogue_id": dialogue_id,
                            "line_number": line_number,
                            "event_index": event_index,
                            "reason": str(exc),
                        }
                    )
                    continue
                events.append(event)
                events_written += 1

        output_rows.append(
            {
                "dialogue_id": dialogue_id,
                "dialogue": _normalize_dialogue_lines(row.get("dialogue")),
                "events": events,
            }
        )

    _write_jsonl(output_path, output_rows)
    _write_jsonl(failure_path, failures)
    return {
        "dialogues_written": len(output_rows),
        "events_written": events_written,
        "events_failed": len(failures),
    }


def evaluate_event_extraction(
    *,
    gold_jsonl: Path,
    pred_jsonl: Path,
    summary_output: Path,
    details_output: Path,
    row_audit_output: Path | None = None,
) -> dict[str, object]:
    gold_dialogues = _read_dialogue_jsonl(gold_jsonl)
    pred_dialogues = _read_dialogue_jsonl(pred_jsonl)

    details: list[dict[str, object]] = []
    row_audits: list[dict[str, object]] = []
    field_totals = {field_name: {"tp": 0, "fp": 0, "fn": 0} for field_name in FIELD_NAMES}
    matched_event_scores: list[float] = []
    matched_events = 0
    unmatched_gold = 0
    unmatched_pred = 0
    alignment_scores: list[float] = []

    for dialogue_id in sorted(set(gold_dialogues) | set(pred_dialogues)):
        gold_events = gold_dialogues.get(dialogue_id, [])
        pred_events = pred_dialogues.get(dialogue_id, [])
        alignment = _align_dialogue_events(gold_events, pred_events)
        matched_by_gold = {gold_index: pred_index for gold_index, pred_index, _score in alignment["matches"]}
        matched_pred_indices = {pred_index for _gold_index, pred_index, _score in alignment["matches"]}
        pair_alignments = alignment["pair_alignments"]
        row_audits.append(
            _build_row_alignment_audit(
                dialogue_id=dialogue_id,
                gold_events=gold_events,
                pred_events=pred_events,
                alignment=alignment,
            )
        )

        for gold_index, gold_event in enumerate(gold_events):
            pred_index = matched_by_gold.get(gold_index)
            if pred_index is None:
                unmatched_gold += 1
                field_details = _build_unmatched_fields(gold_event, None)
                _add_field_scores(field_totals, field_details)
                details.append(
                    {
                        "dialogue_id": dialogue_id,
                        "event_index": gold_index,
                        "gold_event_index": gold_index,
                        "pred_event_index": None,
                        "match_status": "unmatched_gold",
                        "weighted_f1": 0.0,
                        "active_weight": 0.0,
                        "alignment_score": 0.0,
                        "alignment_fields": {},
                        "fields": field_details,
                    }
                )
                continue
            pred_event = pred_events[pred_index]
            pair_alignment = pair_alignments[(gold_index, pred_index)]
            matched_events += 1
            alignment_scores.append(float(pair_alignment["score"]))
            field_details: dict[str, dict[str, object]] = {}
            weighted_score_total = 0.0
            active_weight = 0.0
            for field_name in FIELD_NAMES:
                field_score = _score_field(
                    _normalize_event_field(gold_event.get(field_name)),
                    _normalize_event_field(pred_event.get(field_name)),
                )
                field_details[field_name] = field_score
                if field_score["gold"] or field_score["pred"]:
                    weight = FIELD_WEIGHTS[field_name]
                    active_weight += weight
                    weighted_score_total += weight * float(field_score["f1"])
            _add_field_scores(field_totals, field_details)

            weighted_f1 = _round_metric(weighted_score_total / active_weight) if active_weight else 0.0
            matched_event_scores.append(weighted_f1)
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": gold_index,
                    "gold_event_index": gold_index,
                    "pred_event_index": pred_index,
                    "match_status": "matched",
                    "weighted_f1": weighted_f1,
                    "active_weight": _round_metric(active_weight),
                    "alignment_score": _round_metric(float(pair_alignment["score"])),
                    "alignment_fields": pair_alignment["fields"],
                    "fields": field_details,
                }
            )

        for pred_index, pred_event in enumerate(pred_events):
            if pred_index in matched_pred_indices:
                continue
            unmatched_pred += 1
            field_details = _build_unmatched_fields(None, pred_event)
            _add_field_scores(field_totals, field_details)
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": pred_index,
                    "gold_event_index": None,
                    "pred_event_index": pred_index,
                    "match_status": "unmatched_pred",
                    "weighted_f1": 0.0,
                    "active_weight": 0.0,
                    "alignment_score": 0.0,
                    "alignment_fields": {},
                    "fields": field_details,
                }
            )

    events_evaluated = matched_events + unmatched_gold + unmatched_pred
    summary = _build_summary(
        field_totals=field_totals,
        matched_event_scores=matched_event_scores,
        events_evaluated=events_evaluated,
        matched_events=matched_events,
        unmatched_gold=unmatched_gold,
        unmatched_pred=unmatched_pred,
        alignment_scores=alignment_scores,
    )
    _write_json(summary_output, summary)
    _write_jsonl(details_output, details)
    if row_audit_output is not None:
        _write_jsonl(row_audit_output, row_audits)
    return summary


def evaluate_event_extraction_semantic(
    *,
    gold_jsonl: Path,
    pred_jsonl: Path,
    summary_output: Path,
    details_output: Path,
    row_audit_output: Path,
    judge_audit_output: Path,
    judge: object,
    judge_remote_server_id: str,
    judge_model_id: str,
) -> dict[str, object]:
    gold_dialogues = _read_dialogue_jsonl_rows(gold_jsonl)
    pred_dialogues = _read_dialogue_jsonl_rows(pred_jsonl)
    judge_runtime = _SemanticJudgeRuntime(
        judge=judge,
        judge_remote_server_id=judge_remote_server_id,
        judge_model_id=judge_model_id,
    )

    details: list[dict[str, object]] = []
    row_audits: list[dict[str, object]] = []
    field_totals = {field_name: {"tp": 0, "fp": 0, "fn": 0} for field_name in FIELD_NAMES}
    matched_event_scores: list[float] = []
    matched_events = 0
    unmatched_gold = 0
    unmatched_pred = 0
    alignment_scores: list[float] = []

    for dialogue_id in sorted(set(gold_dialogues) | set(pred_dialogues)):
        gold_row = gold_dialogues.get(dialogue_id, {"events": [], "dialogue": []})
        pred_row = pred_dialogues.get(dialogue_id, {"events": [], "dialogue": []})
        gold_events = gold_row["events"] if isinstance(gold_row.get("events"), list) else []
        pred_events = pred_row["events"] if isinstance(pred_row.get("events"), list) else []
        dialogue = gold_row["dialogue"] if isinstance(gold_row.get("dialogue"), list) else []
        if not dialogue and isinstance(pred_row.get("dialogue"), list):
            dialogue = pred_row["dialogue"]

        alignment = _semantic_align_dialogue_events(
            dialogue_id=dialogue_id,
            dialogue=dialogue,
            gold_events=gold_events,
            pred_events=pred_events,
            judge_runtime=judge_runtime,
        )
        matched_by_gold = {gold_index: pred_index for gold_index, pred_index, _score in alignment["matches"]}
        matched_pred_indices = {pred_index for _gold_index, pred_index, _score in alignment["matches"]}
        alignment_by_pair = {
            (gold_index, pred_index): pair
            for pair in alignment.get("pair_decisions", [])
            if isinstance(pair, dict)
            for gold_index, pred_index in [
                (int(pair.get("gold_event_index", -1)), int(pair.get("pred_event_index", -1)))
            ]
        }
        row_audit = _build_semantic_row_alignment_audit(
            dialogue_id=dialogue_id,
            gold_events=gold_events,
            pred_events=pred_events,
            alignment=alignment,
        )
        row_audits.append(row_audit)

        for gold_index, gold_event in enumerate(gold_events):
            pred_index = matched_by_gold.get(gold_index)
            if pred_index is None:
                unmatched_gold += 1
                field_details = _build_unmatched_fields(gold_event, None)
                _add_field_scores(field_totals, field_details)
                details.append(
                    {
                        "dialogue_id": dialogue_id,
                        "event_index": gold_index,
                        "gold_event_index": gold_index,
                        "pred_event_index": None,
                        "match_status": "unmatched_gold",
                        "weighted_f1": 0.0,
                        "active_weight": 0.0,
                        "alignment_score": 0.0,
                        "semantic_alignment_score": 0.0,
                        "alignment_fields": {},
                        "fields": field_details,
                    }
                )
                continue

            pred_event = pred_events[pred_index]
            pair_decision = alignment_by_pair.get((gold_index, pred_index), {})
            matched_events += 1
            semantic_alignment_score = float(pair_decision.get("alignment_score", 0.0) or 0.0)
            alignment_scores.append(semantic_alignment_score)
            field_details: dict[str, dict[str, object]] = {}
            weighted_score_total = 0.0
            active_weight = 0.0
            for field_name in FIELD_NAMES:
                field_score = _semantic_score_field(
                    dialogue_id=dialogue_id,
                    dialogue=dialogue,
                    field_name=field_name,
                    gold_event_index=gold_index,
                    pred_event_index=pred_index,
                    gold_event=gold_event,
                    pred_event=pred_event,
                    judge_runtime=judge_runtime,
                )
                field_details[field_name] = field_score
                if field_score["gold"] or field_score["pred"]:
                    weight = FIELD_WEIGHTS[field_name]
                    active_weight += weight
                    weighted_score_total += weight * float(field_score["f1"])
            _add_field_scores(field_totals, field_details)

            weighted_f1 = _round_metric(weighted_score_total / active_weight) if active_weight else 0.0
            matched_event_scores.append(weighted_f1)
            if weighted_f1 < SEMANTIC_LOW_QUALITY_ALIGNMENT_WEIGHTED_F1_THRESHOLD:
                row_audit["low_quality_alignment"] = True
                low_quality_pairs = row_audit.setdefault("low_quality_alignment_pairs", [])
                if isinstance(low_quality_pairs, list):
                    low_quality_pairs.append(
                        {
                            "gold_event_index": gold_index,
                            "pred_event_index": pred_index,
                            "weighted_f1": weighted_f1,
                            "alignment_score": _round_metric(semantic_alignment_score),
                        }
                    )
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": gold_index,
                    "gold_event_index": gold_index,
                    "pred_event_index": pred_index,
                    "match_status": "matched",
                    "weighted_f1": weighted_f1,
                    "active_weight": _round_metric(active_weight),
                    "alignment_score": _round_metric(semantic_alignment_score),
                    "semantic_alignment_score": _round_metric(semantic_alignment_score),
                    "alignment_fields": pair_decision.get("alignment_fields", {}),
                    "fields": field_details,
                }
            )

        for pred_index, pred_event in enumerate(pred_events):
            if pred_index in matched_pred_indices:
                continue
            unmatched_pred += 1
            field_details = _build_unmatched_fields(None, pred_event)
            _add_field_scores(field_totals, field_details)
            details.append(
                {
                    "dialogue_id": dialogue_id,
                    "event_index": pred_index,
                    "gold_event_index": None,
                    "pred_event_index": pred_index,
                    "match_status": "unmatched_pred",
                    "weighted_f1": 0.0,
                    "active_weight": 0.0,
                    "alignment_score": 0.0,
                    "semantic_alignment_score": 0.0,
                    "alignment_fields": {},
                    "fields": field_details,
                }
            )

    events_evaluated = matched_events + unmatched_gold + unmatched_pred
    summary = _build_summary(
        field_totals=field_totals,
        matched_event_scores=matched_event_scores,
        events_evaluated=events_evaluated,
        matched_events=matched_events,
        unmatched_gold=unmatched_gold,
        unmatched_pred=unmatched_pred,
        alignment_scores=alignment_scores,
    )
    status = "completed" if judge_runtime.failures == 0 else "partial"
    summary["status"] = status
    summary["scoring_mode"] = SEMANTIC_SCORING_MODE
    summary["base_scoring_mode"] = "event_extraction_weighted_f1"
    summary["alignment_strategy"] = SEMANTIC_EVENT_ALIGNMENT_STRATEGY
    summary["event_alignment"]["alignment_strategy"] = SEMANTIC_EVENT_ALIGNMENT_STRATEGY
    summary["semantic_judge"] = {
        "judge_remote_server_id": judge_runtime.judge_remote_server_id,
        "judge_model_id": judge_runtime.judge_model_id,
        "judge_prompt_version": SEMANTIC_JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
        "calls": judge_runtime.calls,
        "cache_hits": judge_runtime.cache_hits,
        "failures": judge_runtime.failures,
    }

    _write_json(summary_output, summary)
    _write_jsonl(details_output, details)
    _write_jsonl(row_audit_output, row_audits)
    _write_jsonl(judge_audit_output, judge_runtime.audit_rows)
    return summary


class _SemanticJudgeRuntime:
    def __init__(
        self,
        *,
        judge: object,
        judge_remote_server_id: str,
        judge_model_id: str,
    ) -> None:
        self.judge = judge
        self.judge_remote_server_id = judge_remote_server_id
        self.judge_model_id = judge_model_id
        self.calls = 0
        self.cache_hits = 0
        self.failures = 0
        self.cache: dict[str, dict[str, object]] = {}
        self.audit_rows: list[dict[str, object]] = []

    def decide(self, request: dict[str, object]) -> dict[str, object]:
        cache_key = _semantic_judge_cache_key(request)
        if cache_key in self.cache:
            self.cache_hits += 1
            decision = dict(self.cache[cache_key])
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="cache",
                    status="ok",
                    error_code=None,
                    failure_reason=None,
                )
            )
            return decision

        self.calls += 1
        try:
            raw_decision = getattr(self.judge, "judge_semantic_equivalence")(request)
            decision = _normalize_semantic_judge_decision(raw_decision)
            self.cache[cache_key] = decision
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="ok",
                    error_code=None,
                    failure_reason=None,
                )
            )
            return decision
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            failure_reason = _semantic_judge_failure_reason(exc)
            decision = {
                "equivalent": False,
                "confidence": 0.0,
                "reason_code": getattr(exc, "code", "judge_error"),
                "short_reason": failure_reason,
            }
            self.audit_rows.append(
                _semantic_judge_audit_row(
                    request=request,
                    decision=decision,
                    cache_key=cache_key,
                    source="judge",
                    status="failed",
                    error_code=str(getattr(exc, "code", "judge_error")),
                    failure_reason=failure_reason,
                )
            )
            return decision


def _semantic_align_dialogue_events(
    *,
    dialogue_id: str,
    dialogue: list[str],
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
    judge_runtime: _SemanticJudgeRuntime,
) -> dict[str, object]:
    scores: list[list[float]] = []
    accepted: list[list[bool]] = []
    candidate_scores: list[dict[str, object]] = []
    pair_decisions: list[dict[str, object]] = []
    for gold_index, gold_event in enumerate(gold_events):
        score_row: list[float] = []
        accepted_row: list[bool] = []
        for pred_index, pred_event in enumerate(pred_events):
            local_alignment = _event_alignment(gold_event, pred_event)
            local_score = float(local_alignment["score"])
            if bool(local_alignment["accepted"]) and local_score >= 0.999:
                decision = {
                    "equivalent": True,
                    "confidence": 1.0,
                    "reason_code": "deterministic_exact",
                    "short_reason": "Local exact/high-confidence alignment.",
                }
                source = "deterministic"
            elif local_score < SEMANTIC_JUDGE_PREFILTER_SCORE_THRESHOLD:
                decision = {
                    "equivalent": False,
                    "confidence": 0.0,
                    "reason_code": "prefilter_rejected",
                    "short_reason": "Local similarity below semantic judge prefilter.",
                }
                source = "prefilter"
            else:
                decision = judge_runtime.decide(
                    _semantic_event_request(
                        dialogue_id=dialogue_id,
                        dialogue=dialogue,
                        gold_event_index=gold_index,
                        pred_event_index=pred_index,
                        gold_event=gold_event,
                        pred_event=pred_event,
                    )
                )
                source = "judge"
            score = _semantic_decision_score(decision)
            is_accepted = score >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD
            score_row.append(score)
            accepted_row.append(is_accepted)
            candidate = {
                "gold_event_index": gold_index,
                "pred_event_index": pred_index,
                "alignment_score": _round_metric(score),
                "accepted": is_accepted,
                "source": source,
                "reason_code": decision.get("reason_code", ""),
                "local_alignment_score": local_alignment["score"],
            }
            candidate_scores.append(candidate)
            pair_decisions.append(
                {
                    **candidate,
                    "alignment_fields": local_alignment.get("fields", {}),
                    "confidence": _round_metric(float(decision.get("confidence", 0.0) or 0.0)),
                    "equivalent": bool(decision.get("equivalent", False)),
                    "short_reason": str(decision.get("short_reason") or ""),
                }
            )
        scores.append(score_row)
        accepted.append(accepted_row)

    matches = _maximum_weight_event_matching(scores, accepted)
    return {
        "matches": matches,
        "candidate_scores": candidate_scores,
        "pair_decisions": pair_decisions,
    }


def _semantic_score_field(
    *,
    dialogue_id: str,
    dialogue: list[str],
    field_name: str,
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    judge_runtime: _SemanticJudgeRuntime,
) -> dict[str, object]:
    gold_values = _semantic_field_values(field_name, gold_event)
    pred_values = _semantic_field_values(field_name, pred_event)
    if not gold_values or not pred_values:
        score = _score_field(gold_values, pred_values)
        score["semantic_matches"] = []
        return score
    if field_name == "action":
        return _semantic_score_action_field(
            dialogue_id=dialogue_id,
            dialogue=dialogue,
            gold_event_index=gold_event_index,
            pred_event_index=pred_event_index,
            gold_event=gold_event,
            pred_event=pred_event,
            gold_values=gold_values,
            pred_values=pred_values,
            judge_runtime=judge_runtime,
        )

    scores: list[list[float]] = []
    accepted: list[list[bool]] = []
    for gold_index, gold_value in enumerate(gold_values):
        score_row: list[float] = []
        accepted_row: list[bool] = []
        for pred_index, pred_value in enumerate(pred_values):
            score, _reason_code = _semantic_field_value_score(
                dialogue_id=dialogue_id,
                dialogue=dialogue,
                field_name=field_name,
                gold_event_index=gold_event_index,
                pred_event_index=pred_event_index,
                gold_event=gold_event,
                pred_event=pred_event,
                gold_value=gold_value,
                pred_value=pred_value,
                judge_runtime=judge_runtime,
            )
            score_row.append(score)
            accepted_row.append(score >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD)
        scores.append(score_row)
        accepted.append(accepted_row)

    matches = _maximum_weight_event_matching(scores, accepted)
    tp = len(matches)
    fp = len(pred_values) - tp
    fn = len(gold_values) - tp
    return {
        "gold": gold_values,
        "pred": pred_values,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _round_metric(_safe_divide(tp, tp + fp)),
        "recall": _round_metric(_safe_divide(tp, tp + fn)),
        "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
        "semantic_matches": [
            {
                "gold_value": gold_values[gold_index],
                "pred_value": pred_values[pred_index],
                "score": _round_metric(score),
            }
            for gold_index, pred_index, score in matches
        ],
    }


def _semantic_score_action_field(
    *,
    dialogue_id: str,
    dialogue: list[str],
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    gold_values: list[str],
    pred_values: list[str],
    judge_runtime: _SemanticJudgeRuntime,
) -> dict[str, object]:
    candidates: list[dict[str, object]] = []

    for gold_index, gold_value in enumerate(gold_values):
        for pred_index, pred_value in enumerate(pred_values):
            score, reason_code = _semantic_field_value_score(
                dialogue_id=dialogue_id,
                dialogue=dialogue,
                field_name="action",
                gold_event_index=gold_event_index,
                pred_event_index=pred_event_index,
                gold_event=gold_event,
                pred_event=pred_event,
                gold_value=gold_value,
                pred_value=pred_value,
                judge_runtime=judge_runtime,
            )
            if score >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD:
                candidates.append(
                    {
                        "gold_indices": (gold_index,),
                        "pred_indices": (pred_index,),
                        "score": score,
                        "reason_code": reason_code,
                    }
                )

    for gold_index, gold_value in enumerate(gold_values):
        for pred_indices in _semantic_value_groups(len(pred_values)):
            pred_group = [pred_values[index] for index in pred_indices]
            score, reason_code = _semantic_action_group_score(
                dialogue_id=dialogue_id,
                dialogue=dialogue,
                gold_event_index=gold_event_index,
                pred_event_index=pred_event_index,
                gold_event=gold_event,
                pred_event=pred_event,
                gold_values=[gold_value],
                pred_values=pred_group,
                judge_runtime=judge_runtime,
            )
            if score >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD:
                candidates.append(
                    {
                        "gold_indices": (gold_index,),
                        "pred_indices": pred_indices,
                        "score": score,
                        "reason_code": reason_code,
                    }
                )

    for gold_indices in _semantic_value_groups(len(gold_values)):
        gold_group = [gold_values[index] for index in gold_indices]
        for pred_index, pred_value in enumerate(pred_values):
            score, reason_code = _semantic_action_group_score(
                dialogue_id=dialogue_id,
                dialogue=dialogue,
                gold_event_index=gold_event_index,
                pred_event_index=pred_event_index,
                gold_event=gold_event,
                pred_event=pred_event,
                gold_values=gold_group,
                pred_values=[pred_value],
                judge_runtime=judge_runtime,
            )
            if score >= SEMANTIC_JUDGE_CONFIDENCE_THRESHOLD:
                candidates.append(
                    {
                        "gold_indices": gold_indices,
                        "pred_indices": (pred_index,),
                        "score": score,
                        "reason_code": reason_code,
                    }
                )

    matches = _maximum_weight_semantic_value_group_matching(
        candidates,
        gold_count=len(gold_values),
        pred_count=len(pred_values),
    )
    consumed_gold = {
        index
        for match in matches
        for index in match["gold_indices"]
        if isinstance(match.get("gold_indices"), tuple)
    }
    consumed_pred = {
        index
        for match in matches
        for index in match["pred_indices"]
        if isinstance(match.get("pred_indices"), tuple)
    }
    tp = len(matches)
    fp = len(pred_values) - len(consumed_pred)
    fn = len(gold_values) - len(consumed_gold)
    return {
        "gold": gold_values,
        "pred": pred_values,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _round_metric(_safe_divide(tp, tp + fp)),
        "recall": _round_metric(_safe_divide(tp, tp + fn)),
        "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
        "semantic_matches": [
            _semantic_action_match_payload(match, gold_values=gold_values, pred_values=pred_values)
            for match in matches
        ],
    }


def _semantic_field_value_score(
    *,
    dialogue_id: str,
    dialogue: list[str],
    field_name: str,
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    gold_value: str,
    pred_value: str,
    judge_runtime: _SemanticJudgeRuntime,
) -> tuple[float, str]:
    if gold_value == pred_value:
        return 1.0, "exact_value"
    if field_name == "actor" and _actor_slot_relation_conflict(gold_value, pred_value):
        return 0.0, "actor_slot_relation_conflict"
    if field_name == "time" and _obvious_time_conflict(gold_value, pred_value):
        return 0.0, "local_time_conflict"
    decision = judge_runtime.decide(
        _semantic_field_request(
            dialogue_id=dialogue_id,
            dialogue=dialogue,
            field_name=field_name,
            gold_event_index=gold_event_index,
            pred_event_index=pred_event_index,
            gold_event=gold_event,
            pred_event=pred_event,
            gold_value=gold_value,
            pred_value=pred_value,
        )
    )
    return _semantic_decision_score(decision), str(decision.get("reason_code") or "")


def _semantic_action_group_score(
    *,
    dialogue_id: str,
    dialogue: list[str],
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    gold_values: list[str],
    pred_values: list[str],
    judge_runtime: _SemanticJudgeRuntime,
) -> tuple[float, str]:
    decision = judge_runtime.decide(
        _semantic_action_group_request(
            dialogue_id=dialogue_id,
            dialogue=dialogue,
            gold_event_index=gold_event_index,
            pred_event_index=pred_event_index,
            gold_event=gold_event,
            pred_event=pred_event,
            gold_values=gold_values,
            pred_values=pred_values,
        )
    )
    return _semantic_decision_score(decision), str(decision.get("reason_code") or "")


@lru_cache(maxsize=32)
def _semantic_value_groups(value_count: int) -> tuple[tuple[int, ...], ...]:
    groups: list[tuple[int, ...]] = []
    max_size = min(SEMANTIC_ACTION_GROUP_MAX_SIZE, value_count)
    for group_size in range(2, max_size + 1):
        groups.extend(tuple(group) for group in combinations(range(value_count), group_size))
    return tuple(groups)


def _maximum_weight_semantic_value_group_matching(
    candidates: list[dict[str, object]],
    *,
    gold_count: int,
    pred_count: int,
) -> list[dict[str, object]]:
    ordered_candidates = sorted(
        candidates,
        key=lambda candidate: (
            tuple(candidate.get("gold_indices", ())),
            tuple(candidate.get("pred_indices", ())),
            -float(candidate.get("score", 0.0) or 0.0),
        ),
    )
    memo: dict[tuple[int, int, int], tuple[float, int, tuple[int, ...]]] = {}

    def better(
        candidate: tuple[float, int, tuple[int, ...]],
        current: tuple[float, int, tuple[int, ...]],
    ) -> bool:
        if candidate[0] > current[0] + 1e-12:
            return True
        if abs(candidate[0] - current[0]) <= 1e-12:
            if candidate[1] > current[1]:
                return True
            if candidate[1] == current[1]:
                return candidate[2] < current[2]
        return False

    def solve(candidate_index: int, used_gold_mask: int, used_pred_mask: int) -> tuple[float, int, tuple[int, ...]]:
        key = (candidate_index, used_gold_mask, used_pred_mask)
        if key in memo:
            return memo[key]
        if candidate_index >= len(ordered_candidates):
            return (0.0, 0, ())

        best = solve(candidate_index + 1, used_gold_mask, used_pred_mask)
        candidate = ordered_candidates[candidate_index]
        gold_indices = tuple(
            index
            for index in candidate.get("gold_indices", ())
            if isinstance(index, int) and 0 <= index < gold_count
        )
        pred_indices = tuple(
            index
            for index in candidate.get("pred_indices", ())
            if isinstance(index, int) and 0 <= index < pred_count
        )
        gold_mask = sum(1 << index for index in gold_indices)
        pred_mask = sum(1 << index for index in pred_indices)
        if gold_indices and pred_indices and not (used_gold_mask & gold_mask) and not (used_pred_mask & pred_mask):
            next_score, next_consumed, next_indices = solve(
                candidate_index + 1,
                used_gold_mask | gold_mask,
                used_pred_mask | pred_mask,
            )
            score = float(candidate.get("score", 0.0) or 0.0)
            consumed = len(gold_indices) + len(pred_indices)
            taken = (score + next_score, consumed + next_consumed, (candidate_index,) + next_indices)
            if better(taken, best):
                best = taken
        memo[key] = best
        return best

    _score, _consumed, indices = solve(0, 0, 0)
    return [ordered_candidates[index] for index in indices]


def _semantic_action_match_payload(
    match: dict[str, object],
    *,
    gold_values: list[str],
    pred_values: list[str],
) -> dict[str, object]:
    gold_indices = tuple(index for index in match.get("gold_indices", ()) if isinstance(index, int))
    pred_indices = tuple(index for index in match.get("pred_indices", ()) if isinstance(index, int))
    score = _round_metric(float(match.get("score", 0.0) or 0.0))
    if len(gold_indices) == 1 and len(pred_indices) == 1:
        return {
            "gold_value": gold_values[gold_indices[0]],
            "pred_value": pred_values[pred_indices[0]],
            "score": score,
        }
    return {
        "gold_values": [gold_values[index] for index in gold_indices],
        "pred_values": [pred_values[index] for index in pred_indices],
        "score": score,
    }


def _semantic_field_values(field_name: str, event: dict[str, object]) -> list[str]:
    values = _normalize_unique_event_field(event.get(field_name))
    if field_name != "actor":
        return values
    return list(_expanded_semantic_actor_values(tuple(values)))


def _normalize_unique_event_field(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("event field values must be null or a list of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("event field values must be null or a list of strings")
        stripped = item.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        normalized.append(stripped)
    return normalized


@lru_cache(maxsize=512)
def _expanded_semantic_actor_values(values: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    seen_expanded: set[str] = set()
    for value in values:
        if _is_group_actor_alias(value):
            expansion = ("speaker_1", "speaker_2")
        else:
            expansion = (value,)
        for expanded_value in expansion:
            if expanded_value in seen_expanded:
                continue
            seen_expanded.add(expanded_value)
            expanded.append(expanded_value)
    return tuple(expanded)


def _obvious_time_conflict(left: str, right: str) -> bool:
    normalized_left = _normalize_similarity_text(left)
    normalized_right = _normalize_similarity_text(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return False
    relative_terms = ("今天", "今晚", "明天", "明晚", "后天", "后晚", "昨天", "昨晚")
    left_relative = any(term in normalized_left for term in relative_terms)
    right_relative = any(term in normalized_right for term in relative_terms)
    left_numeric = any(character.isdigit() for character in normalized_left)
    right_numeric = any(character.isdigit() for character in normalized_right)
    if left_relative != right_relative and left_numeric != right_numeric:
        return True
    return False


def _actor_slot_relation_conflict(left: str, right: str) -> bool:
    normalized_left = _normalize_similarity_text(left)
    normalized_right = _normalize_similarity_text(right)
    speaker_slots = {"speaker1", "speaker2"}
    if normalized_left in speaker_slots and normalized_right in speaker_slots:
        return normalized_left != normalized_right
    for speaker_slot in ("speaker1", "speaker2"):
        if normalized_left == speaker_slot and normalized_right.startswith(f"{speaker_slot}的"):
            return True
        if normalized_right == speaker_slot and normalized_left.startswith(f"{speaker_slot}的"):
            return True
    return False


def _semantic_decision_score(decision: dict[str, object]) -> float:
    if not bool(decision.get("equivalent", False)):
        return 0.0
    confidence = decision.get("confidence", 0.0)
    if isinstance(confidence, bool):
        return 0.0
    if not isinstance(confidence, (int, float)):
        return 0.0
    return _round_metric(max(0.0, min(1.0, float(confidence))))


def _semantic_event_request(
    *,
    dialogue_id: str,
    dialogue: list[str],
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
) -> dict[str, object]:
    return {
        "kind": "event",
        "dialogue_id": dialogue_id,
        "gold_event_index": gold_event_index,
        "pred_event_index": pred_event_index,
        "gold_event": _semantic_event_payload(gold_event),
        "pred_event": _semantic_event_payload(pred_event),
        "dialogue_excerpt": _dialogue_excerpt(dialogue),
    }


def _semantic_field_request(
    *,
    dialogue_id: str,
    dialogue: list[str],
    field_name: str,
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    gold_value: str,
    pred_value: str,
) -> dict[str, object]:
    return {
        "kind": "field",
        "dialogue_id": dialogue_id,
        "field_name": field_name,
        "gold_value": gold_value,
        "pred_value": pred_value,
        "gold_event_index": gold_event_index,
        "pred_event_index": pred_event_index,
        "gold_event": _semantic_event_payload(gold_event),
        "pred_event": _semantic_event_payload(pred_event),
        "dialogue_excerpt": _dialogue_excerpt(dialogue),
    }


def _semantic_action_group_request(
    *,
    dialogue_id: str,
    dialogue: list[str],
    gold_event_index: int,
    pred_event_index: int,
    gold_event: dict[str, object],
    pred_event: dict[str, object],
    gold_values: list[str],
    pred_values: list[str],
) -> dict[str, object]:
    return {
        "kind": "field",
        "comparison_type": "action_group",
        "dialogue_id": dialogue_id,
        "field_name": "action",
        "gold_value": ",".join(gold_values),
        "pred_value": ",".join(pred_values),
        "gold_values": gold_values,
        "pred_values": pred_values,
        "gold_event_index": gold_event_index,
        "pred_event_index": pred_event_index,
        "gold_event": _semantic_event_payload(gold_event),
        "pred_event": _semantic_event_payload(pred_event),
        "dialogue_excerpt": _dialogue_excerpt(dialogue),
    }


def _semantic_event_payload(event: dict[str, object]) -> dict[str, object]:
    return {field_name: _normalize_event_field(event.get(field_name)) for field_name in FIELD_NAMES}


def _dialogue_excerpt(dialogue: list[str]) -> list[str]:
    return [line for line in dialogue[:8] if isinstance(line, str) and line.strip()]


def _normalize_semantic_judge_decision(raw_decision: object) -> dict[str, object]:
    if not isinstance(raw_decision, dict):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response was not a JSON object.",
        }
    equivalent = raw_decision.get("equivalent")
    if not isinstance(equivalent, bool):
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": "Judge response did not contain a boolean equivalent field.",
        }
    confidence_value = raw_decision.get("confidence", 0.0)
    confidence = 0.0
    if not isinstance(confidence_value, bool) and isinstance(confidence_value, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence_value)))
    reason_code = raw_decision.get("reason_code")
    short_reason = raw_decision.get("short_reason")
    if str(reason_code or "").strip() == "uncertain":
        equivalent = False
    return {
        "equivalent": equivalent,
        "confidence": _round_metric(confidence),
        "reason_code": str(reason_code or ("same_value" if equivalent else "uncertain")).strip(),
        "short_reason": str(short_reason or "").strip(),
    }


def _parse_semantic_judge_response(response_text: str) -> dict[str, object]:
    try:
        return _normalize_semantic_judge_decision(_parse_response_json(response_text))
    except Exception as exc:  # noqa: BLE001
        return {
            "equivalent": False,
            "confidence": 0.0,
            "reason_code": "malformed_response",
            "short_reason": str(exc),
        }


def _semantic_judge_cache_key(request: dict[str, object]) -> str:
    payload = {
        key: value
        for key, value in request.items()
        if key not in {"dialogue_id", "dialogue_excerpt", "gold_event_index", "pred_event_index"}
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _semantic_judge_failure_reason(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return f"remote provider HTTP {status_code}"
    if isinstance(exc, RemoteProviderRequestError):
        return "remote provider request failed"
    first_line = str(exc).splitlines()[0].strip()
    if not first_line:
        return exc.__class__.__name__
    return first_line[:240]


def _semantic_judge_audit_row(
    *,
    request: dict[str, object],
    decision: dict[str, object],
    cache_key: str,
    source: str,
    status: str,
    error_code: str | None,
    failure_reason: str | None,
) -> dict[str, object]:
    return {
        "dialogue_id": request.get("dialogue_id", ""),
        "kind": request.get("kind", ""),
        "judge_prompt_version": SEMANTIC_JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": SEMANTIC_JUDGE_PROMPT_HASH,
        "field_name": request.get("field_name"),
        "comparison_type": request.get("comparison_type"),
        "gold_event_index": request.get("gold_event_index"),
        "pred_event_index": request.get("pred_event_index"),
        "gold_value": request.get("gold_value"),
        "pred_value": request.get("pred_value"),
        "gold_values": request.get("gold_values"),
        "pred_values": request.get("pred_values"),
        "equivalent": bool(decision.get("equivalent", False)),
        "confidence": _round_metric(float(decision.get("confidence", 0.0) or 0.0)),
        "reason_code": str(decision.get("reason_code") or ""),
        "short_reason": str(decision.get("short_reason") or ""),
        "source": source,
        "status": status,
        "cache_key": cache_key,
        "error_code": error_code,
        "failure_reason": failure_reason,
    }


def _unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _normalize_optional_string_list(value: object, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be null or an array of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must be null or an array of strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized or None


def _normalize_event_field(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("event field values must be null or a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("event field values must be null or a list of strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized


def _score_field(gold_values: list[str], pred_values: list[str]) -> dict[str, object]:
    gold_set = set(gold_values)
    pred_set = set(pred_values)
    tp = len(gold_set & pred_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    return {
        "gold": gold_values,
        "pred": pred_values,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _round_metric(_safe_divide(tp, tp + fp)),
        "recall": _round_metric(_safe_divide(tp, tp + fn)),
        "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
    }


def _align_dialogue_events(
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
) -> dict[str, object]:
    scores: list[list[float]] = []
    accepted: list[list[bool]] = []
    candidate_scores: list[dict[str, object]] = []
    pair_alignments: dict[tuple[int, int], dict[str, object]] = {}
    for gold_index, gold_event in enumerate(gold_events):
        score_row: list[float] = []
        accepted_row: list[bool] = []
        for pred_index, pred_event in enumerate(pred_events):
            alignment = _event_alignment(gold_event, pred_event)
            pair_alignments[(gold_index, pred_index)] = alignment
            score = float(alignment["score"])
            is_accepted = bool(alignment["accepted"])
            score_row.append(score)
            accepted_row.append(is_accepted)
            candidate_scores.append(
                {
                    "gold_event_index": gold_index,
                    "pred_event_index": pred_index,
                    "alignment_score": _round_metric(score),
                    "accepted": is_accepted,
                }
            )
        scores.append(score_row)
        accepted.append(accepted_row)

    matches = _maximum_weight_event_matching(scores, accepted)
    return {
        "matches": matches,
        "candidate_scores": candidate_scores,
        "pair_alignments": pair_alignments,
    }


def _event_alignment(gold_event: dict[str, object], pred_event: dict[str, object]) -> dict[str, object]:
    field_scores: dict[str, float] = {}
    active_weight = 0.0
    weighted_score = 0.0
    gold_actions: list[str] = []
    pred_actions: list[str] = []
    for field_name in FIELD_NAMES:
        gold_values = _normalize_event_field(gold_event.get(field_name))
        pred_values = _normalize_event_field(pred_event.get(field_name))
        if field_name == "action":
            gold_actions = gold_values
            pred_actions = pred_values
        field_score = _soft_field_f1(gold_values, pred_values)
        field_scores[field_name] = _round_metric(field_score)
        if gold_values or pred_values:
            weight = FIELD_WEIGHTS[field_name]
            active_weight += weight
            weighted_score += weight * field_score
    score = weighted_score / active_weight if active_weight else 0.0
    action_score = field_scores["action"]
    accepted = score >= EVENT_ALIGNMENT_SCORE_THRESHOLD
    if gold_actions and pred_actions and action_score < EVENT_ALIGNMENT_ACTION_THRESHOLD:
        accepted = False
    return {
        "score": _round_metric(score),
        "accepted": accepted,
        "fields": field_scores,
    }


def _soft_field_f1(gold_values: list[str], pred_values: list[str]) -> float:
    if not gold_values and not pred_values:
        return 0.0
    if not gold_values or not pred_values:
        return 0.0
    scores: list[list[float]] = [
        [_string_similarity(gold_value, pred_value) for pred_value in pred_values]
        for gold_value in gold_values
    ]
    accepted = [[score > 0.0 for score in row] for row in scores]
    matches = _maximum_weight_event_matching(scores, accepted)
    soft_tp = sum(score for _gold_index, _pred_index, score in matches)
    return _safe_divide(2.0 * soft_tp, len(gold_values) + len(pred_values))


@lru_cache(maxsize=8192)
def _string_similarity(left: str, right: str) -> float:
    normalized_left = _normalize_similarity_text(left)
    normalized_right = _normalize_similarity_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    containment_score = 0.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        containment_score = 1.0
    return max(containment_score, _bigram_dice(normalized_left, normalized_right))


@lru_cache(maxsize=4096)
def _normalize_similarity_text(value: str) -> str:
    return "".join(char for char in value.strip().lower() if char not in _SIMILARITY_IGNORED_CHARS)


_NORMALIZED_GROUP_ACTOR_ALIASES = frozenset(
    _normalize_similarity_text(alias) for alias in _GROUP_ACTOR_ALIASES
)


@lru_cache(maxsize=512)
def _is_group_actor_alias(value: str) -> bool:
    if value in _GROUP_ACTOR_ALIASES:
        return True
    for char in value:
        if char not in _SIMILARITY_IGNORED_CHARS and char not in _GROUP_ACTOR_ALIAS_CHARS:
            return False
    return _normalize_similarity_text(value) in _NORMALIZED_GROUP_ACTOR_ALIASES


def _bigram_dice(left: str, right: str) -> float:
    left_units = _character_bigram_items(left)
    right_units = _character_bigram_items(right)
    if not left_units or not right_units:
        return 0.0
    overlap = 0
    remaining = dict(right_units)
    for unit, count in left_units:
        matched = min(count, remaining.get(unit, 0))
        overlap += matched
        if matched:
            remaining[unit] = remaining.get(unit, 0) - matched
    return _safe_divide(
        2.0 * overlap,
        sum(count for _unit, count in left_units) + sum(count for _unit, count in right_units),
    )


def _character_bigrams(value: str) -> dict[str, int]:
    return dict(_character_bigram_items(value))


@lru_cache(maxsize=4096)
def _character_bigram_items(value: str) -> tuple[tuple[str, int], ...]:
    if len(value) <= 1:
        return ((value, 1),) if value else ()
    counts: dict[str, int] = {}
    for index in range(len(value) - 1):
        unit = value[index : index + 2]
        counts[unit] = counts.get(unit, 0) + 1
    return tuple(counts.items())


def _accepted_event_matching_edges(
    scores: list[list[float]],
    accepted: list[list[bool]],
) -> tuple[tuple[tuple[int, float], ...], ...]:
    return tuple(
        tuple(
            (pred_index, float(score))
            for pred_index, score in enumerate(score_row)
            if pred_index < len(accepted_row) and accepted_row[pred_index]
        )
        for score_row, accepted_row in zip(scores, accepted, strict=False)
    )


def _maximum_weight_event_matching(
    scores: list[list[float]],
    accepted: list[list[bool]],
) -> list[tuple[int, int, float]]:
    gold_count = len(scores)
    accepted_edges = _accepted_event_matching_edges(scores, accepted)
    memo: dict[tuple[int, int], tuple[float, tuple[tuple[int, int, float], ...]]] = {}

    def better(
        candidate: tuple[float, tuple[tuple[int, int, float], ...]],
        current: tuple[float, tuple[tuple[int, int, float], ...]],
    ) -> bool:
        if candidate[0] > current[0] + 1e-12:
            return True
        if abs(candidate[0] - current[0]) <= 1e-12:
            return candidate[1] < current[1]
        return False

    def solve(gold_index: int, used_pred_mask: int) -> tuple[float, tuple[tuple[int, int, float], ...]]:
        key = (gold_index, used_pred_mask)
        if key in memo:
            return memo[key]
        if gold_index >= gold_count:
            return (0.0, ())

        best = solve(gold_index + 1, used_pred_mask)
        for pred_index, score in accepted_edges[gold_index]:
            if used_pred_mask & (1 << pred_index):
                continue
            next_score, next_pairs = solve(gold_index + 1, used_pred_mask | (1 << pred_index))
            pair = (gold_index, pred_index, _round_metric(score))
            candidate = (score + next_score, (pair,) + next_pairs)
            if better(candidate, best):
                best = candidate
        memo[key] = best
        return best

    return list(solve(0, 0)[1])


def _build_row_alignment_audit(
    *,
    dialogue_id: str,
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
    alignment: dict[str, object],
) -> dict[str, object]:
    matches = alignment["matches"] if isinstance(alignment.get("matches"), list) else []
    matched_gold = {gold_index for gold_index, _pred_index, _score in matches}
    matched_pred = {pred_index for _gold_index, pred_index, _score in matches}
    return {
        "dialogue_id": dialogue_id,
        "alignment_strategy": EVENT_ALIGNMENT_STRATEGY,
        "gold_event_count": len(gold_events),
        "pred_event_count": len(pred_events),
        "matched_pairs": [
            {
                "gold_event_index": gold_index,
                "pred_event_index": pred_index,
                "alignment_score": _round_metric(score),
            }
            for gold_index, pred_index, score in matches
        ],
        "unmatched_gold_indices": [
            gold_index for gold_index in range(len(gold_events)) if gold_index not in matched_gold
        ],
        "unmatched_pred_indices": [
            pred_index for pred_index in range(len(pred_events)) if pred_index not in matched_pred
        ],
        "candidate_scores": alignment.get("candidate_scores", []),
    }


def _build_semantic_row_alignment_audit(
    *,
    dialogue_id: str,
    gold_events: list[dict[str, object]],
    pred_events: list[dict[str, object]],
    alignment: dict[str, object],
) -> dict[str, object]:
    matches = alignment["matches"] if isinstance(alignment.get("matches"), list) else []
    matched_gold = {gold_index for gold_index, _pred_index, _score in matches}
    matched_pred = {pred_index for _gold_index, pred_index, _score in matches}
    return {
        "dialogue_id": dialogue_id,
        "alignment_strategy": SEMANTIC_EVENT_ALIGNMENT_STRATEGY,
        "gold_event_count": len(gold_events),
        "pred_event_count": len(pred_events),
        "matched_pairs": [
            {
                "gold_event_index": gold_index,
                "pred_event_index": pred_index,
                "alignment_score": _round_metric(score),
            }
            for gold_index, pred_index, score in matches
        ],
        "unmatched_gold_indices": [
            gold_index for gold_index in range(len(gold_events)) if gold_index not in matched_gold
        ],
        "unmatched_pred_indices": [
            pred_index for pred_index in range(len(pred_events)) if pred_index not in matched_pred
        ],
        "candidate_scores": alignment.get("candidate_scores", []),
        "low_quality_alignment": False,
        "low_quality_alignment_threshold": SEMANTIC_LOW_QUALITY_ALIGNMENT_WEIGHTED_F1_THRESHOLD,
        "low_quality_alignment_pairs": [],
    }


def _build_summary(
    *,
    field_totals: dict[str, dict[str, int]],
    matched_event_scores: Sequence[float],
    events_evaluated: int,
    matched_events: int,
    unmatched_gold: int,
    unmatched_pred: int,
    alignment_scores: Sequence[float],
) -> dict[str, object]:
    field_metrics: dict[str, dict[str, object]] = {}
    hallucination_rates: dict[str, float] = {}
    missing_rates: dict[str, float] = {}

    for field_name in FIELD_NAMES:
        totals = field_totals[field_name]
        tp = totals["tp"]
        fp = totals["fp"]
        fn = totals["fn"]
        field_metrics[field_name] = {
            "weight": FIELD_WEIGHTS[field_name],
            "precision": _round_metric(_safe_divide(tp, tp + fp)),
            "recall": _round_metric(_safe_divide(tp, tp + fn)),
            "f1": _round_metric(_safe_divide(2 * tp, 2 * tp + fp + fn)),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        hallucination_rates[field_name] = _round_metric(_safe_divide(fp, tp + fp))
        missing_rates[field_name] = _round_metric(_safe_divide(fn, tp + fn))

    event_summary = {
        "overall_weighted_f1": _round_metric(
            _safe_divide(sum(matched_event_scores), events_evaluated)
        ),
        "events_evaluated": events_evaluated,
        "events_matched": matched_events,
        "events_unmatched_gold": unmatched_gold,
        "events_unmatched_pred": unmatched_pred,
    }
    alignment_summary = {
        "matched_pairs": matched_events,
        "unmatched_gold": unmatched_gold,
        "unmatched_pred": unmatched_pred,
        "mean_alignment_score": _round_metric(_safe_divide(sum(alignment_scores), len(alignment_scores))),
        "min_alignment_score": _round_metric(min(alignment_scores)) if alignment_scores else 0.0,
        "alignment_score_threshold": EVENT_ALIGNMENT_SCORE_THRESHOLD,
        "action_score_threshold": EVENT_ALIGNMENT_ACTION_THRESHOLD,
    }
    return {
        **event_summary,
        "alignment_strategy": EVENT_ALIGNMENT_STRATEGY,
        "summary": event_summary,
        "event_alignment": alignment_summary,
        "field_metrics": field_metrics,
        "rates": {
            "hallucination_rate_by_field": hallucination_rates,
            "missing_rate_by_field": missing_rates,
        },
        "weights": dict(FIELD_WEIGHTS),
    }


def _read_dialogue_jsonl(path: Path) -> dict[str, list[dict[str, object]]]:
    dialogues: dict[str, list[dict[str, object]]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            dialogue_id = row.get("dialogue_id")
            if not isinstance(dialogue_id, str) or not dialogue_id:
                raise ValueError(f"missing dialogue_id at {path}:{line_number}")
            events = row.get("events")
            if not isinstance(events, list):
                raise ValueError(f"events must be a list at {path}:{line_number}")
            dialogues[dialogue_id] = [event for event in events if isinstance(event, dict)]
    return dialogues


def _read_dialogue_jsonl_rows(path: Path) -> dict[str, dict[str, object]]:
    dialogues: dict[str, dict[str, object]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            dialogue_id = row.get("dialogue_id")
            if not isinstance(dialogue_id, str) or not dialogue_id:
                raise ValueError(f"missing dialogue_id at {path}:{line_number}")
            events = row.get("events")
            if not isinstance(events, list):
                raise ValueError(f"events must be a list at {path}:{line_number}")
            dialogues[dialogue_id] = {
                "dialogue": _normalize_dialogue_lines(row.get("dialogue")),
                "events": [event for event in events if isinstance(event, dict)],
            }
    return dialogues


def _build_unmatched_fields(
    gold_event: dict[str, object] | None,
    pred_event: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    return {
        field_name: _score_field(
            _normalize_event_field(gold_event.get(field_name)) if gold_event is not None else [],
            _normalize_event_field(pred_event.get(field_name)) if pred_event is not None else [],
        )
        for field_name in FIELD_NAMES
    }


def _add_field_scores(
    field_totals: dict[str, dict[str, int]],
    field_details: dict[str, dict[str, object]],
) -> None:
    for field_name in FIELD_NAMES:
        field_score = field_details[field_name]
        field_totals[field_name]["tp"] += int(field_score["tp"])
        field_totals[field_name]["fp"] += int(field_score["fp"])
        field_totals[field_name]["fn"] += int(field_score["fn"])


def _normalize_dialogue_lines(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _assistant_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("remote provider response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("remote provider choice must be a JSON object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("remote provider choice did not include a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("remote provider message content must be a string")
    return content


def _gemini_content(response: dict[str, object]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("remote provider response did not include candidates")
    first = candidates[0]
    if not isinstance(first, dict):
        raise ValueError("remote provider candidate must be a JSON object")
    content = first.get("content")
    if not isinstance(content, dict):
        raise ValueError("remote provider candidate did not include content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise ValueError("remote provider candidate content did not include parts")
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    if not text_parts:
        raise ValueError("remote provider candidate parts did not include text")
    return "".join(text_parts)


def _openai_provider_usage(response: dict[str, object]) -> dict[str, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    return _provider_usage_from_keys(
        usage,
        (
            ("prompt_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens"),
        ),
    )


def _gemini_provider_usage(response: dict[str, object]) -> dict[str, int]:
    usage = response.get("usageMetadata")
    if not isinstance(usage, dict):
        return {}
    return _provider_usage_from_keys(
        usage,
        (
            ("promptTokenCount", "prompt_tokens"),
            ("candidatesTokenCount", "completion_tokens"),
            ("totalTokenCount", "total_tokens"),
        ),
    )


def _provider_usage_from_keys(usage: dict[object, object], key_map: Sequence[tuple[str, str]]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for source_key, target_key in key_map:
        value = usage.get(source_key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            normalized[target_key] = value
        elif isinstance(value, float) and value.is_integer():
            normalized[target_key] = int(value)
    return normalized


def _gemini_model_path(model_id: str) -> str:
    trimmed = model_id.strip()
    path = trimmed if trimmed.startswith("models/") else f"models/{trimmed}"
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _openai_example_messages(
    examples: Sequence[dict[str, object]],
    prompt_input_mode: str = "raw_dialogue",
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for example in examples:
        messages.append({"role": "user", "content": _example_dialogue_text(example, prompt_input_mode)})
        messages.append({"role": "assistant", "content": _example_response_text(example, prompt_input_mode)})
    return messages


def _gemini_example_contents(
    examples: Sequence[dict[str, object]],
    prompt_input_mode: str = "raw_dialogue",
) -> list[dict[str, object]]:
    contents: list[dict[str, object]] = []
    for example in examples:
        contents.append(
            {
                "role": "user",
                "parts": [{"text": _example_dialogue_text(example, prompt_input_mode)}],
            }
        )
        contents.append(
            {
                "role": "model",
                "parts": [{"text": _example_response_text(example, prompt_input_mode)}],
            }
        )
    return contents


def _example_dialogue_text(example: dict[str, object], prompt_input_mode: str = "raw_dialogue") -> str:
    return _dialogue_user_content(
        _normalize_dialogue_lines(example.get("dialogue")),
        str(example.get("dialogue_id") or "").strip(),
        prompt_input_mode,
    )


def _example_response_text(example: dict[str, object], prompt_input_mode: str = "raw_dialogue") -> str:
    events = example.get("events")
    normalized_events: list[dict[str, object]] = []
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                normalized_events.append({field_name: event.get(field_name) for field_name in FIELD_NAMES})
    if prompt_input_mode == "stage1":
        return json.dumps(
            _stage1_response_payload_from_events(normalized_events),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if prompt_input_mode == "direct_event_json":
        return json.dumps(
            _direct_event_response_payload_from_events(
                dialogue_id=str(example.get("dialogue_id") or "").strip(),
                events=normalized_events,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return json.dumps({"events": normalized_events}, ensure_ascii=False, separators=(",", ":"))


def _prompt_input_mode(prompt_spec: EventExtractionPromptSpec) -> str:
    if _prompt_uses_stage1_schema(prompt_spec):
        return "stage1"
    if _prompt_uses_direct_event_json_schema(prompt_spec):
        return "direct_event_json"
    return "raw_dialogue"


def _prompt_uses_stage1_schema(prompt_spec: EventExtractionPromptSpec) -> bool:
    prompt = prompt_spec.system_prompt
    return "event_candidates" in prompt and "conversation" in prompt and "stage-1" in prompt


def _prompt_uses_direct_event_json_schema(prompt_spec: EventExtractionPromptSpec) -> bool:
    prompt = prompt_spec.system_prompt
    return '"dialogue_id"' in prompt and '"source_order"' in prompt and "你是中文对话事件抽取器" in prompt


def _dialogue_user_content(
    dialogue: Sequence[str],
    dialogue_id: str = "",
    prompt_input_mode: str = "raw_dialogue",
) -> str:
    if prompt_input_mode == "stage1":
        return json.dumps(
            _dialogue_segment_payload(dialogue, dialogue_id),
            ensure_ascii=False,
            indent=2,
        )
    if prompt_input_mode == "direct_event_json":
        return json.dumps(
            {
                "dialogue_id": dialogue_id.strip(),
                "dialogue": _normalize_dialogue_lines(list(dialogue)),
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        return "\n".join(_normalize_dialogue_lines(list(dialogue)))


def _dialogue_segment_payload(dialogue: Sequence[str], dialogue_id: str = "") -> dict[str, object]:
    normalized_dialogue = _normalize_dialogue_lines(list(dialogue))
    conversation: list[dict[str, object]] = []
    participant_set: list[dict[str, str]] = []
    seen_participants: set[str] = set()

    for index, line in enumerate(normalized_dialogue, start=1):
        sender, text = _split_dialogue_line(line)
        participant_id = sender or f"speaker_{index}"
        if participant_id not in seen_participants:
            participant_set.append(
                {
                    "participant_id": participant_id,
                    "display_name": participant_id,
                }
            )
            seen_participants.add(participant_id)
        conversation.append(
            {
                "message_id": f"m{index}",
                "sender": sender or participant_id,
                "participant_id": participant_id,
                "timestamp": None,
                "text": text,
            }
        )

    segment_id = dialogue_id.strip() or "segment-1"
    return {
        "segment": {
            "segment_id": segment_id,
            "dialogue_id": dialogue_id.strip() or None,
            "message_count": len(conversation),
        },
        "participant_set": participant_set,
        "conversation": conversation,
    }


def _split_dialogue_line(line: str) -> tuple[str, str]:
    for delimiter in (":", "："):
        if delimiter in line:
            prefix, text = line.split(delimiter, 1)
            sender = prefix.strip()
            if sender:
                return sender, text.strip()
    return "", line.strip()


def _stage1_response_payload_from_events(events: Sequence[dict[str, object]]) -> dict[str, object]:
    event_candidates = []
    for event in events:
        event_candidates.append(
            {
                "participants": _coerce_string_list(event.get("actor")),
                "time": _coerce_string_list(event.get("time")),
                "location": _coerce_string_list(event.get("location")),
                "action": ", ".join(_coerce_string_list(event.get("action"))),
                "status": "planned",
                "detail": None,
                "confidence": 1.0,
                "evidence": ["m1"],
            }
        )
    return {
        "boundary_decision": {
            "starts_new_dialogue": False,
            "new_dialogue_start_message_id": None,
            "boundary_confidence": 0.0,
            "boundary_reason": "no_restart",
        },
        "entity_mentions": [],
        "time_mentions": [],
        "location_mentions": [],
        "topic_candidates": [],
        "digest_candidates": [],
        "event_candidates": event_candidates,
        "issues": [],
    }


def _direct_event_response_payload_from_events(
    *,
    dialogue_id: str,
    events: Sequence[dict[str, object]],
) -> dict[str, object]:
    direct_events: list[dict[str, object]] = []
    for index, event in enumerate(events, start=1):
        actor = event.get("actor")
        time = event.get("time")
        location = event.get("location")
        action = event.get("action")
        digest = event.get("digest")
        direct_events.append(
            {
                "actor": actor,
                "time": time,
                "location": location,
                "action": action,
                "digest": str(digest).strip()
                if isinstance(digest, str) and digest.strip()
                else build_event_digest(
                    actor=_coerce_string_list(actor) or None,
                    time=_coerce_string_list(time) or None,
                    location=_coerce_string_list(location) or None,
                    action=_coerce_string_list(action) or None,
                ),
                "source_order": index,
            }
        )
    return {"dialogue_id": dialogue_id, "events": direct_events}


def _event_from_candidate(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "actor": _coerce_string_list(candidate.get("participants", candidate.get("actor"))),
        "time": _coerce_string_list(candidate.get("time")),
        "location": _coerce_string_list(candidate.get("location")),
        "action": _coerce_action(candidate.get("action")),
    }


def _coerce_action(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else None
    return _coerce_string_list(value)


def _coerce_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


def _parse_response_json(response_text: str) -> dict[str, object]:
    stripped = response_text.strip()
    if stripped.startswith("```"):
        newline_index = stripped.find("\n")
        if newline_index >= 0 and stripped.endswith("```"):
            stripped = stripped[newline_index + 1 : -3].strip()
        else:
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _round_metric(value: float) -> float:
    return round(value, 6)
