import CryptoKit
import Foundation

public enum EvaluationPromptRevisionStatus: String, Codable, Equatable, Sendable {
    case draft
    case frozen
}

public struct EvaluationPromptExampleEvent: Codable, Equatable, Sendable {
    public let actor: [String]?
    public let time: [String]?
    public let location: [String]?
    public let action: [String]?

    public init(
        actor: [String]? = nil,
        time: [String]? = nil,
        location: [String]? = nil,
        action: [String]? = nil
    ) {
        self.actor = actor
        self.time = time
        self.location = location
        self.action = action
    }
}

public struct EvaluationPromptExample: Codable, Equatable, Sendable {
    public let dialogueID: String
    public let dialogue: [String]
    public let events: [EvaluationPromptExampleEvent]

    public init(dialogueID: String, dialogue: [String], events: [EvaluationPromptExampleEvent]) {
        self.dialogueID = dialogueID
        self.dialogue = dialogue
        self.events = events
    }

    enum CodingKeys: String, CodingKey {
        case dialogueID = "dialogue_id"
        case dialogue
        case events
    }
}

public struct EvaluationPromptRevision: Codable, Equatable, Sendable, Identifiable {
    public let revisionID: String
    public let status: EvaluationPromptRevisionStatus
    public let systemPrompt: String
    public let examples: [EvaluationPromptExample]
    public let contentHash: String
    public let createdAt: Date
    public let updatedAt: Date

    public var id: String { revisionID }

    public init(
        revisionID: String,
        status: EvaluationPromptRevisionStatus,
        systemPrompt: String,
        examples: [EvaluationPromptExample] = [],
        contentHash: String,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.revisionID = revisionID
        self.status = status
        self.systemPrompt = systemPrompt
        self.examples = examples
        self.contentHash = contentHash
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case revisionID = "revision_id"
        case status
        case systemPrompt = "system_prompt"
        case examples
        case contentHash = "content_hash"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

public struct EvaluationPrompt: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let title: String
    public let taskKind: String
    public let scoringMode: String
    public let latestRevisionID: String
    public let archived: Bool
    public let readOnly: Bool
    public let revisions: [EvaluationPromptRevision]
    public let createdAt: Date
    public let updatedAt: Date

    public init(
        id: String,
        title: String,
        taskKind: String = EvaluationPromptStore.eventExtractionTaskKind,
        scoringMode: String = EvaluationPromptStore.eventExtractionScoringMode,
        latestRevisionID: String,
        archived: Bool = false,
        readOnly: Bool = false,
        revisions: [EvaluationPromptRevision],
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.taskKind = taskKind
        self.scoringMode = scoringMode
        self.latestRevisionID = latestRevisionID
        self.archived = archived
        self.readOnly = readOnly
        self.revisions = revisions
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var latestRevision: EvaluationPromptRevision? {
        revisions.first { $0.revisionID == latestRevisionID } ?? revisions.last
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case latestRevisionID = "latest_revision_id"
        case archived
        case readOnly = "read_only"
        case revisions
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

public struct EvaluationPromptSnapshot: Codable, Equatable, Sendable {
    public let promptID: String
    public let title: String
    public let taskKind: String
    public let scoringMode: String
    public let revisionID: String
    public let status: EvaluationPromptRevisionStatus
    public let systemPrompt: String
    public let examples: [EvaluationPromptExample]
    public let contentHash: String
    public let readOnly: Bool

    public init(prompt: EvaluationPrompt, revision: EvaluationPromptRevision) {
        self.promptID = prompt.id
        self.title = prompt.title
        self.taskKind = prompt.taskKind
        self.scoringMode = prompt.scoringMode
        self.revisionID = revision.revisionID
        self.status = revision.status
        self.systemPrompt = revision.systemPrompt
        self.examples = revision.examples
        self.contentHash = revision.contentHash
        self.readOnly = prompt.readOnly
    }

    enum CodingKeys: String, CodingKey {
        case promptID = "prompt_id"
        case title
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case revisionID = "revision_id"
        case status
        case systemPrompt = "system_prompt"
        case examples
        case contentHash = "content_hash"
        case readOnly = "read_only"
    }
}

public struct EvaluationPromptStore: Sendable {
    public static let eventExtractionTaskKind = "event_extraction"
    public static let eventExtractionScoringMode = "event_extraction_weighted_f1"
    public static let topicMembershipTaskKind = "topic_membership"
    public static let topicMembershipStrictScoringMode = "topic_membership_strict_micro_f1"
    public static let topicMembershipSemanticScoringMode = "topic_membership_semantic_micro_f1"
    public static let topicMembershipScoringModes: Set<String> = [
        topicMembershipStrictScoringMode,
        topicMembershipSemanticScoringMode,
    ]
    public static let builtInBaselinePromptID = "builtin.event-extraction.baseline"
    public static let builtInLegacyBaselineRevisionID = "baseline.v1"
    public static let builtInStage1BaselineRevisionID = "baseline.v2"
    public static let builtInDirectJSONBaselineRevisionID = "baseline.v3"
    public static let builtInFeedbackBaselineRevisionID = "baseline.v4"
    public static let builtInFeedbackV5BaselineRevisionID = "baseline.v5"
    public static let builtInBaselineRevisionID = "baseline.v6"
    public static let builtInLegacyBaselineSystemPrompt = """
    Extract established events and future plans from a dialogue.

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
    public static let builtInStage1BaselineSystemPrompt = """
    # Segment Metadata Candidates

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

    public static let builtInDirectJSONBaselineSystemPrompt = """
    你是中文对话事件抽取器。请根据输入的 dialogue 生成 events。

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

    public static let builtInFeedbackBaselineSystemPrompt = builtInDirectJSONBaselineSystemPrompt + """

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

    public static let builtInFeedbackV5BaselineSystemPrompt = builtInFeedbackBaselineSystemPrompt + """

    11. 反馈案例约束
    - “同地点同时吃饭”不等于“共同吃饭”。例如一方在对方店里请别人吃饭，另一方也和朋友吃饭，应按各自事件分别抽取，不要把 speaker_1 和 speaker_2 合并成同一个 actor 数组。
    - “订桌/找人订桌”和“约饭/吃饭”如果只是同一吃饭安排的准备步骤，保留吃饭或见面的主事件；除非订桌本身有独立完成价值，否则不要抽取为独立事件。
    - “拿位”“占座”“排队”等微动作通常是见面或吃饭的准备动作，不要抽取为独立事件。
    - “出来转转”“喝东西坐坐”“逛街买衣服”这类复合活动应保留成一个自然事件，不要拆成多个互相重复的事件。
    - “糖筛/唐筛”如果模型不确定具体写法，优先输出上位动作“做检查”，不要编造更细的检查项目。
    """

    public static let builtInBaselineSystemPrompt = builtInFeedbackV5BaselineSystemPrompt + """

    12. 召回强化与新反馈约束
    - 明确的过去事件、背景事件和已发生状态也要抽取，不只抽未来计划。例如“周日新买裙子”应抽为 speaker_1 周日 新买裙子或新进碎花长裙。
    - 明确承诺的电话联系要抽取。例如“明天打给你”应抽为拨打电话事件，不要因为它是联系动作而丢弃。
    - 明确航班、飞机、落地或出发时间要抽取。例如“周一晚上11点下飞机”和“周二晚上7点上飞机”是两个有时间锚点的旅行事件。
    - 同事/朋友/表姐等模糊第三方关系词通常进入 action 细节，例如“和同事聚餐”“和朋友吃饭”“和同事看话剧”；actor 只保留实际对话参与者，除非第三方本身是事件主体。
    - 继续避免准备动作、重复事件和微动作成为独立事件。订桌、拿位、占座、重复聚会等如果只是主事件的一部分，应并入吃饭、见面、聚会等主事件。
    - 保持时间区间、候选时间、同地点不合并 actor、复合活动不过度拆分等 baseline.v5 规则。
    """

    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func list(includeArchived: Bool = false) throws -> [EvaluationPrompt] {
        let customPrompts = try loadDocument().prompts
            .filter { includeArchived || $0.archived == false }
            .sorted { $0.id < $1.id }
        return [Self.builtInBaselinePrompt] + customPrompts
    }

    public func get(id: String) throws -> EvaluationPrompt? {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "prompt_id")
        if normalizedID == Self.builtInBaselinePromptID {
            return Self.builtInBaselinePrompt
        }
        return try loadDocument().prompts.first { $0.id == normalizedID }
    }

    public func resolveForRun(promptID: String = "", revisionID: String = "") throws -> EvaluationPromptSnapshot {
        let normalizedPromptID = promptID.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = try get(id: normalizedPromptID.isEmpty ? Self.builtInBaselinePromptID : normalizedPromptID)
        guard let prompt else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedPromptID) was not found.")
        }
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) is archived.")
        }
        let revision = try Self.revision(
            in: prompt,
            revisionID: revisionID,
            fallbackToLatest: true
        )
        guard revision.status == .frozen else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) revision \(revision.revisionID) is not frozen.")
        }
        return EvaluationPromptSnapshot(prompt: prompt, revision: revision)
    }

    @discardableResult
    public func create(promptID: String, title: String, systemPrompt: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        let normalizedTitle = try Self.normalizedRequired(title, fieldName: "title")
        let normalizedPrompt = try Self.normalizedRequired(systemPrompt, fieldName: "system_prompt")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard document.prompts.contains(where: { $0.id == normalizedID }) == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) already exists.")
        }
        let now = Date()
        let revision = try Self.makeRevision(
            revisionID: "rev-1",
            status: .draft,
            systemPrompt: normalizedPrompt,
            examples: [],
            createdAt: now,
            updatedAt: now
        )
        let prompt = EvaluationPrompt(
            id: normalizedID,
            title: normalizedTitle,
            latestRevisionID: revision.revisionID,
            revisions: [revision],
            createdAt: now,
            updatedAt: now
        )
        document.prompts.append(prompt)
        document.prompts.sort { $0.id < $1.id }
        try saveDocument(document)
        return prompt
    }

    @discardableResult
    public func update(promptID: String, systemPrompt: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        let normalizedPrompt = try Self.normalizedRequired(systemPrompt, fieldName: "system_prompt")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) is archived.")
        }
        let now = Date()
        var revisions = prompt.revisions
        var latestRevisionID = prompt.latestRevisionID
        if let latestIndex = revisions.firstIndex(where: { $0.revisionID == prompt.latestRevisionID }),
           revisions[latestIndex].status == .draft
        {
            let existing = revisions[latestIndex]
            revisions[latestIndex] = try Self.makeRevision(
                revisionID: existing.revisionID,
                status: .draft,
                systemPrompt: normalizedPrompt,
                examples: existing.examples,
                createdAt: existing.createdAt,
                updatedAt: now
            )
        } else {
            let baseExamples = prompt.latestRevision?.examples ?? []
            let revisionID = "rev-\(revisions.count + 1)"
            let revision = try Self.makeRevision(
                revisionID: revisionID,
                status: .draft,
                systemPrompt: normalizedPrompt,
                examples: baseExamples,
                createdAt: now,
                updatedAt: now
            )
            revisions.append(revision)
            latestRevisionID = revisionID
        }
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: latestRevisionID,
            archived: false,
            readOnly: false,
            revisions: revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    @discardableResult
    public func freeze(promptID: String, revisionID: String = "") throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        guard normalizedID != Self.builtInBaselinePromptID else {
            return Self.builtInBaselinePrompt
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) is archived.")
        }
        let revision = try Self.revision(in: prompt, revisionID: revisionID, fallbackToLatest: true)
        guard revision.status == .draft else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) revision \(revision.revisionID) is already frozen.")
        }
        var revisions = prompt.revisions
        let now = Date()
        guard let revisionIndex = revisions.firstIndex(where: { $0.revisionID == revision.revisionID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) revision \(revision.revisionID) was not found.")
        }
        revisions[revisionIndex] = try Self.makeRevision(
            revisionID: revision.revisionID,
            status: .frozen,
            systemPrompt: revision.systemPrompt,
            examples: revision.examples,
            createdAt: revision.createdAt,
            updatedAt: now
        )
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: revision.revisionID,
            archived: false,
            readOnly: false,
            revisions: revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    @discardableResult
    public func archive(promptID: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        let now = Date()
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: prompt.latestRevisionID,
            archived: true,
            readOnly: false,
            revisions: prompt.revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    public static func contentHash(
        taskKind: String = eventExtractionTaskKind,
        scoringMode: String = eventExtractionScoringMode,
        systemPrompt: String,
        examples: [EvaluationPromptExample] = []
    ) throws -> String {
        let payload = EvaluationPromptHashPayload(
            taskKind: taskKind,
            scoringMode: scoringMode,
            systemPrompt: systemPrompt,
            examples: examples
        )
        let data = try hashEncoder.encode(payload)
        let digest = SHA256.hash(data: data)
        return "sha256:" + digest.map { String(format: "%02x", $0) }.joined()
    }

    public static func examplesJSONString(_ examples: [EvaluationPromptExample]) throws -> String {
        guard examples.isEmpty == false else {
            return "[]"
        }
        let data = try hashEncoder.encode(examples)
        return String(decoding: data, as: UTF8.self)
    }

    public static var builtInBaselinePrompt: EvaluationPrompt {
        let legacyRevision = try! makeRevision(
            revisionID: builtInLegacyBaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInLegacyBaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let stage1Revision = try! makeRevision(
            revisionID: builtInStage1BaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInStage1BaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let directJSONRevision = try! makeRevision(
            revisionID: builtInDirectJSONBaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInDirectJSONBaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let feedbackRevision = try! makeRevision(
            revisionID: builtInFeedbackBaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInFeedbackBaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let feedbackV5Revision = try! makeRevision(
            revisionID: builtInFeedbackV5BaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInFeedbackV5BaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        let revision = try! makeRevision(
            revisionID: builtInBaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInBaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        return EvaluationPrompt(
            id: builtInBaselinePromptID,
            title: "Built-in Chinese Event Extraction JSON",
            latestRevisionID: revision.revisionID,
            archived: false,
            readOnly: true,
            revisions: [legacyRevision, stage1Revision, directJSONRevision, feedbackRevision, feedbackV5Revision, revision],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    private func loadDocument() throws -> EvaluationPromptDocument {
        guard FileManager.default.fileExists(atPath: melixHome.evaluationPromptsFileURL.path) else {
            return EvaluationPromptDocument()
        }
        let data = try Data(contentsOf: melixHome.evaluationPromptsFileURL)
        return try Self.decoder.decode(EvaluationPromptDocument.self, from: data)
    }

    private func saveDocument(_ document: EvaluationPromptDocument) throws {
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.evaluationPromptsFileURL)
    }

    private static func makeRevision(
        revisionID: String,
        status: EvaluationPromptRevisionStatus,
        systemPrompt: String,
        examples: [EvaluationPromptExample],
        createdAt: Date,
        updatedAt: Date
    ) throws -> EvaluationPromptRevision {
        EvaluationPromptRevision(
            revisionID: revisionID,
            status: status,
            systemPrompt: systemPrompt,
            examples: examples,
            contentHash: try contentHash(systemPrompt: systemPrompt, examples: examples),
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }

    private static func revision(
        in prompt: EvaluationPrompt,
        revisionID: String,
        fallbackToLatest: Bool
    ) throws -> EvaluationPromptRevision {
        let normalizedRevisionID = revisionID.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedRevisionID.isEmpty, fallbackToLatest, let latest = prompt.latestRevision {
            return latest
        }
        guard let revision = prompt.revisions.first(where: { $0.revisionID == normalizedRevisionID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) revision \(normalizedRevisionID) was not found.")
        }
        return revision
    }

    private static func normalizedRequired(_ value: String, fieldName: String) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.isEmpty == false else {
            throw MelixCLIError.missingRequired("\(fieldName) must not be empty.")
        }
        return normalized
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    private static let hashEncoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

private struct EvaluationPromptHashPayload: Codable {
    let taskKind: String
    let scoringMode: String
    let systemPrompt: String
    let examples: [EvaluationPromptExample]

    enum CodingKeys: String, CodingKey {
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case systemPrompt = "system_prompt"
        case examples
    }
}

private struct EvaluationPromptDocument: Codable {
    var schemaVersion: Int
    var prompts: [EvaluationPrompt]

    init(schemaVersion: Int = 1, prompts: [EvaluationPrompt] = []) {
        self.schemaVersion = max(schemaVersion, 1)
        self.prompts = prompts
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case prompts
    }
}
