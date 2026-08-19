"""Dashboard demo dataset (BUILD_PLAN D8-M4 data plane, vision §15).

Authored ``Project Falcon`` content shaped to the real storage models so the
Executive Deal Room frontend renders genuine domain data (no lorem, no fake
labels). The agent roster is read from the real registry seed. When the
dashboard is backed by live Firestore this module is swapped for a Firestore
repository; until then it is the honest, deterministic stand-in (DESIGN.md §9).
"""

from __future__ import annotations

from dashboard.api.models import (
    AgentOut,
    DealBundle,
    DealSummary,
    EvidenceItem,
    FindingDetail,
    FindingListItem,
    InboxEntry,
    QuarantineItem,
    ScorecardGroup,
    SecurityBundle,
    SecurityFeedItem,
    TraceStep,
    WorkstreamProgress,
)
from registry.seed import SEED_MANIFESTS

DEAL_ID = "deal-falcon"

_SUMMARY = DealSummary(
    deal_id=DEAL_ID,
    name="Project Falcon",
    target="Acme Robotics, Inc.",
    deal_type="Acquisition",
    health="HIGH RISK",
    health_tone="critical",
    critical_findings=2,
    high_findings=5,
    open_questions=14,
    documents_reviewed=483,
    agents_active=8,
    security_blocked=10,
    updated_at="2026-08-18T09:41:00Z",
)

_WORKSTREAMS = [
    WorkstreamProgress(workstream="legal", label="Legal", documents=96, findings=4, progress=82),
    WorkstreamProgress(
        workstream="finance", label="Finance", documents=71, findings=3, progress=74
    ),
    WorkstreamProgress(workstream="hr", label="HR", documents=44, findings=2, progress=95),
    WorkstreamProgress(
        workstream="ip_tech", label="IP & Tech", documents=88, findings=3, progress=61
    ),
    WorkstreamProgress(workstream="tax", label="Tax", documents=39, findings=1, progress=52),
    WorkstreamProgress(
        workstream="regulatory", label="Regulatory", documents=57, findings=1, progress=63
    ),
    WorkstreamProgress(workstream="esg", label="ESG", documents=33, findings=1, progress=87),
    WorkstreamProgress(
        workstream="real_estate", label="Real Estate", documents=55, findings=1, progress=78
    ),
]


def _ev(span: str, doc: str, ref: str | None = None) -> EvidenceItem:
    return EvidenceItem(verbatim_span=span, document_id=doc, chunk_ref=ref)


def _step(ts: str, stage: str, actor: str, detail: str) -> TraceStep:
    return TraceStep(ts=ts, stage=stage, actor=actor, detail=detail)


def _finding(
    finding_id: str,
    title: str,
    severity: str,
    workstream: str,
    confidence: float,
    status: str,
    documents: int,
    created_at: str,
    updated_at: str,
    summary: str = "",
    evidence: list[EvidenceItem] | None = None,
    source_documents: list[str] | None = None,
    affected_entities: list[str] | None = None,
    contributing_agents: list[str] | None = None,
    related_findings: list[str] | None = None,
    questions: list[str] | None = None,
    trace: list[TraceStep] | None = None,
) -> FindingDetail:
    return FindingDetail(
        finding_id=finding_id,
        title=title,
        severity=severity,
        workstream=workstream,
        owner=f"{workstream}-agent@{DEAL_ID}",
        confidence=confidence,
        status=status,
        documents=documents,
        created_at=created_at,
        updated_at=updated_at,
        summary=summary,
        evidence=evidence or [],
        source_documents=source_documents or [],
        affected_entities=affected_entities or [],
        contributing_agents=contributing_agents or [f"{workstream}-agent@{DEAL_ID}"],
        related_findings=related_findings or [],
        questions=questions or [],
        trace=trace or [],
    )


_COC_SPAN = (
    "either party may terminate this Agreement within ninety (90) days "
    "following a Change of Control"
)

_FINDINGS: list[FindingDetail] = [
    _finding(
        "SYN-001",
        "Compound customer-exit exposure threatens deal economics",
        "critical",
        "legal",
        0.82,
        "open",
        6,
        "2026-08-18T08:12:00Z",
        "2026-08-18T09:41:00Z",
        summary=(
            "Multi-workstream synthesis: the Customer X change-of-control termination right, "
            "an 18.3% revenue concentration, and the loss of the account owner converge into a "
            "single existential risk. If the CoC clause is triggered at close, Acme could lose "
            "its largest customer and the revenue base the valuation depends on."
        ),
        evidence=[
            _ev(_COC_SPAN, "contract_customer_x.pdf", "clause:11.3"),
            _ev(
                "Meridian Logistics  27,450,000",
                "financials_fy27.xlsx",
                "sheet:FY27 Projected Revenue!rows:3",
            ),
        ],
        source_documents=["contract_customer_x.pdf", "financials_fy27.xlsx", "hr_roster_acme.xlsx"],
        affected_entities=["Meridian Logistics, Inc.", "Customer X"],
        contributing_agents=[
            f"legal-agent@{DEAL_ID}",
            f"finance-agent@{DEAL_ID}",
            f"hr-agent@{DEAL_ID}",
        ],
        related_findings=["LEGAL-014", "FIN-007", "HR-003"],
        questions=[
            "Can the CoC termination right be waived or priced via a purchase adjustment?",
            "What retention package keeps the Meridian account owner through close?",
        ],
        trace=[
            _step(
                "2026-08-17T14:02:11Z",
                "document.parsed",
                "ingestion-pipeline",
                "contract_customer_x.pdf routed to legal",
            ),
            _step(
                "2026-08-17T14:02:19Z",
                "finding.created",
                "legal-agent",
                "CoC termination right detected (clause 11.3)",
            ),
            _step(
                "2026-08-17T14:05:40Z",
                "gateway.decision",
                "gateway",
                "legal to finance ALLOW: revenue share 18.3%",
            ),
            _step(
                "2026-08-18T08:12:03Z",
                "finding.created",
                "coordinator",
                "cross-workstream synthesis SYN-001",
            ),
            _step(
                "2026-08-18T08:12:05Z",
                "finding.escalated",
                "coordination-escalation",
                "escalated to deal lead (critical)",
            ),
        ],
    ),
    _finding(
        "LEGAL-014",
        "Customer X change-of-control termination right",
        "critical",
        "legal",
        0.9,
        "validated",
        2,
        "2026-08-17T14:02:19Z",
        "2026-08-18T08:10:00Z",
        summary=(
            "Section 11.3 of the Meridian Logistics master services agreement grants either "
            "party a unilateral termination right within 90 days of a change of control. The "
            "proposed acquisition is a triggering event."
        ),
        evidence=[_ev(_COC_SPAN, "contract_customer_x.pdf", "clause:11.3")],
        source_documents=["contract_customer_x.pdf"],
        affected_entities=["Meridian Logistics, Inc."],
        related_findings=["FIN-007", "SYN-001"],
        questions=["Is there a carve-out or consent mechanism for an acquisition-triggered CoC?"],
        trace=[
            _step(
                "2026-08-17T14:02:11Z",
                "document.parsed",
                "ingestion-pipeline",
                "contract_customer_x.pdf parsed, clear",
            ),
            _step(
                "2026-08-17T14:02:15Z",
                "data_room.read",
                "legal-agent",
                "read contract_customer_x.pdf",
            ),
            _step(
                "2026-08-17T14:02:19Z",
                "finding.created",
                "legal-agent",
                "evidence-gated finding created",
            ),
        ],
    ),
    _finding(
        "FIN-007",
        "Customer X revenue concentration at 18.3% of FY27 projections",
        "high",
        "finance",
        0.95,
        "validated",
        1,
        "2026-08-17T14:05:40Z",
        "2026-08-17T14:20:00Z",
        summary=(
            "Finance confirmed via the governed gateway that Meridian Logistics (Customer X) "
            "represents 18.3% of projected FY27 revenue. Concentration this size materially "
            "amplifies any customer-termination risk."
        ),
        evidence=[
            _ev(
                "Meridian Logistics  27,450,000",
                "financials_fy27.xlsx",
                "sheet:FY27 Projected Revenue!rows:3",
            )
        ],
        source_documents=["financials_fy27.xlsx"],
        affected_entities=["Meridian Logistics, Inc.", "Customer X"],
        related_findings=["LEGAL-014", "SYN-001"],
        trace=[
            _step(
                "2026-08-17T14:05:38Z",
                "gateway.decision",
                "gateway",
                "ALLOW - aggregate revenue share",
            ),
            _step(
                "2026-08-17T14:05:40Z",
                "finding.created",
                "finance-agent",
                "linked finding FIN-007 (18.3%)",
            ),
        ],
    ),
    _finding(
        "IP-009",
        "TitanBridge 4.1 at vendor end-of-life; migration 9-12 months",
        "high",
        "ip_tech",
        0.9,
        "open",
        2,
        "2026-08-17T15:31:00Z",
        "2026-08-18T07:00:00Z",
        summary=(
            "The Meridian-serving fleet-orchestration subsystem runs TitanBridge 4.1, a "
            "vendor-supported dependency now at end-of-life with no active support contract. "
            "Engineering estimates a 9-12 month migration."
        ),
        evidence=[
            _ev("TitanBridge 4.1  end-of-life  no support contract", "tech_inventory.pdf", "para:9")
        ],
        source_documents=["tech_inventory.pdf"],
        affected_entities=["Fleet Orchestration Platform", "TitanBridge"],
        questions=["Can a support bridge be purchased, or is a rewrite required pre-close?"],
    ),
    _finding(
        "REG-005",
        "EU export authorization lapses for two subsystems",
        "high",
        "regulatory",
        0.78,
        "open",
        3,
        "2026-08-17T16:02:00Z",
        "2026-08-18T06:30:00Z",
        summary=(
            "Two export-controlled subsystems shipped to EU customers rely on authorizations "
            "that lapse within 120 days. Renewal is uncertain and could restrict post-close sales."
        ),
        evidence=[
            _ev(
                "authorization expires 2026-11-30 pending renewal",
                "regulatory_correspondence.pdf",
                "para:4",
            )
        ],
        source_documents=["regulatory_correspondence.pdf"],
        affected_entities=["EU Sales", "Subsystem E-2", "Subsystem E-4"],
    ),
    _finding(
        "RE-004",
        "Meridian facility lease requires landlord consent on change of control",
        "high",
        "real_estate",
        0.85,
        "open",
        1,
        "2026-08-18T05:11:00Z",
        "2026-08-18T05:40:00Z",
        summary=(
            "The primary manufacturing lease contains a change-of-control consent provision. "
            "Landlord consent is a condition to assignment; withholding consent could force "
            "relocation of the Meridian line."
        ),
        evidence=[
            _ev(
                "Assignment requires Landlord's prior written consent upon a Change of Control",
                "lease_meridian.pdf",
                "clause:18.2",
            )
        ],
        source_documents=["lease_meridian.pdf"],
        affected_entities=["Meridian Facility", "Landlord: Northgate Properties"],
    ),
    _finding(
        "HR-003",
        "Key-person risk: Meridian account owner departing",
        "high",
        "hr",
        0.88,
        "open",
        1,
        "2026-08-17T13:22:00Z",
        "2026-08-18T04:00:00Z",
        summary=(
            "Dana Whitfield (VP Customer Success), owner of the Meridian Logistics relationship, "
            "has resigned effective ~60 days out. Departure of the account owner ahead of a CoC "
            "event weakens customer continuity."
        ),
        evidence=[
            _ev(
                "Dana Whitfield  VP Customer Success  resignation effective 2026-10-13",
                "hr_roster_acme.xlsx",
                "sheet:Roster!rows:14",
            )
        ],
        source_documents=["hr_roster_acme.xlsx"],
        affected_entities=["Dana Whitfield", "Meridian Logistics, Inc."],
        questions=["Is a retention or transition plan in place for the Meridian relationship?"],
    ),
    _finding(
        "TAX-002",
        "NOL carryforward at risk under Section 382 limitation",
        "medium",
        "tax",
        0.7,
        "open",
        2,
        "2026-08-17T17:45:00Z",
        "2026-08-17T18:10:00Z",
        summary=(
            "The acquisition is likely an ownership change under IRC Section 382, which would "
            "cap the annual use of Acme's net operating loss carryforwards and reduce the "
            "anticipated tax shield in the buyer's model."
        ),
        evidence=[
            _ev(
                "ownership change may limit utilization of deferred tax assets",
                "tax_exposure.pdf",
                "para:6",
            )
        ],
        source_documents=["tax_exposure.pdf"],
    ),
    _finding(
        "FIN-011",
        "Deferred revenue recognition timing differs FY26 to FY27",
        "medium",
        "finance",
        0.75,
        "validated",
        1,
        "2026-08-17T12:10:00Z",
        "2026-08-17T12:45:00Z",
        summary=(
            "A portion of FY27 projected revenue is deferred under the customer contracts' "
            "milestone schedule; recognition timing should be confirmed in the quality of "
            "earnings analysis."
        ),
        evidence=[
            _ev(
                "deferred revenue recognized on milestone completion",
                "financials_fy27.xlsx",
                "sheet:Notes!rows:7",
            )
        ],
        source_documents=["financials_fy27.xlsx"],
    ),
    _finding(
        "HR-006",
        "Contractor misclassification exposure in field services",
        "medium",
        "hr",
        0.66,
        "open",
        1,
        "2026-08-18T03:05:00Z",
        "2026-08-18T03:30:00Z",
        summary=(
            "A cohort of field-service contractors exhibits employee-like control factors. "
            "Misclassification could create retroactive payroll and benefits exposure."
        ),
        evidence=[
            _ev(
                "field contractors subject to shift scheduling and exclusivity",
                "hr_roster_acme.xlsx",
                "sheet:Contractors!rows:2",
            )
        ],
        source_documents=["hr_roster_acme.xlsx"],
    ),
    _finding(
        "ESG-001",
        "Scope 3 emissions disclosure gap vs buyer ESG covenant",
        "medium",
        "esg",
        0.6,
        "open",
        1,
        "2026-08-17T18:40:00Z",
        "2026-08-17T19:00:00Z",
        summary=(
            "Acme does not currently report Scope 3 emissions. The buyer's standard covenant "
            "requires Scope 3 disclosure within 12 months post-close; a plan and estimate "
            "are needed."
        ),
        evidence=[
            _ev("Scope 1 and 2 reported; Scope 3 not yet measured", "esg_report.pdf", "para:3")
        ],
        source_documents=["esg_report.pdf"],
    ),
    _finding(
        "LEGAL-021",
        "TitanBridge exclusivity extended to 2030 (Section 4 only)",
        "low",
        "legal",
        0.92,
        "resolved",
        1,
        "2026-08-17T15:50:00Z",
        "2026-08-17T16:05:00Z",
        summary=(
            "An amendment extends the TitanBridge exclusivity term to 2030-06-30, but Section 4 "
            "only; the change supersedes the prior vendor agreement and narrows competitive risk."
        ),
        evidence=[
            _ev(
                "exclusivity term is extended through June 30, 2030",
                "amendment_2030.pdf",
                "clause:4.1",
            )
        ],
        source_documents=["amendment_2030.pdf"],
    ),
    _finding(
        "IP-002",
        "Copyleft dependency audit clean for shipped binaries",
        "informational",
        "ip_tech",
        0.97,
        "resolved",
        1,
        "2026-08-17T11:00:00Z",
        "2026-08-17T11:20:00Z",
        summary=(
            "An audit of shipped binaries found no copyleft (GPL/AGPL) obligations that would "
            "encumber the deal. Permissive licenses confirmed with notices present."
        ),
        evidence=[
            _ev(
                "no copyleft obligations identified in shipped artifacts",
                "tech_inventory.pdf",
                "para:2",
            )
        ],
        source_documents=["tech_inventory.pdf"],
    ),
]

_QUARANTINE = [
    QuarantineItem(
        document_id="injection/direct_a.pdf",
        layer="sentinel_tripwire",
        reason_codes=["ignore_instructions"],
        rule_ids=["sentinel.tripwire"],
        attack_class="injection",
        ts="2026-08-18T09:02:11Z",
    ),
    QuarantineItem(
        document_id="injection/direct_b.pdf",
        layer="sentinel_tripwire",
        reason_codes=["ignore_instructions"],
        rule_ids=["sentinel.tripwire"],
        attack_class="injection",
        ts="2026-08-18T09:02:14Z",
    ),
    QuarantineItem(
        document_id="injection/obfuscated/a.pdf",
        layer="sentinel_tripwire",
        reason_codes=["ignore_instructions"],
        rule_ids=["sentinel.tripwire"],
        attack_class="injection",
        ts="2026-08-18T09:02:17Z",
    ),
    QuarantineItem(
        document_id="exfiltration/a.pdf",
        layer="sentinel_tripwire",
        reason_codes=["exfiltration"],
        rule_ids=["sentinel.exfiltration"],
        attack_class="exfiltration",
        ts="2026-08-18T09:02:21Z",
    ),
    QuarantineItem(
        document_id="exfiltration/b.pdf",
        layer="sentinel_tripwire",
        reason_codes=["exfiltration"],
        rule_ids=["sentinel.exfiltration"],
        attack_class="exfiltration",
        ts="2026-08-18T09:02:24Z",
    ),
    QuarantineItem(
        document_id="injection/authority_forgery_a.pdf",
        layer="model_armor",
        reason_codes=["authority_forgery"],
        rule_ids=["authority.forgery"],
        attack_class="injection",
        ts="2026-08-18T09:03:02Z",
    ),
    QuarantineItem(
        document_id="cross_ws/state_mutation_a.pdf",
        layer="model_armor",
        reason_codes=["cross_workstream_mutation"],
        rule_ids=["cross_ws.mutation"],
        attack_class="cross_ws",
        ts="2026-08-18T09:03:06Z",
    ),
    QuarantineItem(
        document_id="cross_ws/privilege_escalation_a.pdf",
        layer="model_armor",
        reason_codes=["privilege_escalation"],
        rule_ids=["cross_ws.privilege_escalation"],
        attack_class="cross_ws",
        ts="2026-08-18T09:03:09Z",
    ),
    QuarantineItem(
        document_id="poisoning/tool_poisoning_a.pdf",
        layer="model_armor",
        reason_codes=["tool_poisoning"],
        rule_ids=["poisoning.tool"],
        attack_class="poisoning",
        ts="2026-08-18T09:03:13Z",
    ),
    QuarantineItem(
        document_id="cross_deal/cross_deal_probe_a.pdf",
        layer="model_armor",
        reason_codes=["cross_deal_probe"],
        rule_ids=["cross_deal.probe"],
        attack_class="cross_deal",
        ts="2026-08-18T09:03:16Z",
    ),
]

_FEED = [
    SecurityFeedItem(
        ts="2026-08-18T09:03:16Z",
        kind="quarantine",
        outcome="blocked",
        subject="cross_deal/cross_deal_probe_a.pdf",
        detail="Model Armor: cross_deal.probe",
    ),
    SecurityFeedItem(
        ts="2026-08-18T09:03:13Z",
        kind="quarantine",
        outcome="blocked",
        subject="poisoning/tool_poisoning_a.pdf",
        detail="Model Armor: poisoning.tool",
    ),
    SecurityFeedItem(
        ts="2026-08-18T09:03:09Z",
        kind="quarantine",
        outcome="blocked",
        subject="cross_ws/privilege_escalation_a.pdf",
        detail="Model Armor: privilege_escalation",
    ),
    SecurityFeedItem(
        ts="2026-08-18T09:03:06Z",
        kind="quarantine",
        outcome="blocked",
        subject="cross_ws/state_mutation_a.pdf",
        detail="Model Armor: cross_workstream_mutation",
    ),
    SecurityFeedItem(
        ts="2026-08-18T09:03:02Z",
        kind="quarantine",
        outcome="blocked",
        subject="injection/authority_forgery_a.pdf",
        detail="Model Armor: authority_forgery",
    ),
    SecurityFeedItem(
        ts="2026-08-18T09:02:24Z",
        kind="tripwire",
        outcome="blocked",
        subject="exfiltration/b.pdf",
        detail="Sentinel tripwire: exfiltration",
    ),
    SecurityFeedItem(
        ts="2026-08-17T16:20:00Z",
        kind="gateway",
        outcome="deny",
        subject="finance-agent",
        detail="legal to finance blocked: RAW_MODEL_PROHIBITED (valuation model internals)",
    ),
    SecurityFeedItem(
        ts="2026-08-17T16:05:00Z",
        kind="authz",
        outcome="deny",
        subject="finance-agent",
        detail="direct read denied: workstream_boundary (contracts)",
    ),
    SecurityFeedItem(
        ts="2026-08-17T14:05:38Z",
        kind="gateway",
        outcome="allow",
        subject="legal-agent",
        detail="legal to finance ALLOW: aggregate revenue share (rate 3/10)",
    ),
    SecurityFeedItem(
        ts="2026-08-17T13:58:00Z",
        kind="authz",
        outcome="deny",
        subject="hr-agent",
        detail="direct read denied: cross_deal (deal-hawk)",
    ),
]

_SCORECARD = [
    ScorecardGroup(group="Prompt Injection", blocked=4, total=4),
    ScorecardGroup(group="Exfiltration", blocked=2, total=2),
    ScorecardGroup(group="Cross-Workstream Leak", blocked=2, total=2),
    ScorecardGroup(group="Tool Poisoning / Cross-Deal", blocked=2, total=2),
]

_INBOX = [
    InboxEntry(
        finding_id="SYN-001",
        title="Compound customer-exit exposure threatens deal economics",
        severity="critical",
        workstream="legal",
        owner=f"coordinator@{DEAL_ID}",
        message=(
            "Critical finding requires deal-lead review: CoC termination x revenue "
            "concentration x key-person risk."
        ),
        status="open",
        created_at="2026-08-18T08:12:05Z",
    ),
    InboxEntry(
        finding_id="LEGAL-014",
        title="Customer X change-of-control termination right",
        severity="critical",
        workstream="legal",
        owner=f"legal-agent@{DEAL_ID}",
        message=(
            "Critical finding requires deal-lead review: CoC termination right triggered "
            "by the acquisition."
        ),
        status="open",
        created_at="2026-08-17T14:02:21Z",
    ),
]


def build_agents() -> list[AgentOut]:
    out: list[AgentOut] = []
    for manifest in SEED_MANIFESTS:
        out.append(
            AgentOut(
                agent_id=manifest.agent_id,
                name=manifest.name,
                workstream=manifest.workstream.value,
                version=manifest.version,
                model_id="gemini-3.5-flash",
                approved=manifest.approved,
                deployment_status="deployed",
                rollback_target=manifest.rollback_target,
                eval_score=0.87,
                capabilities=list(manifest.capabilities),
            )
        )
    return out


def build_deal_bundle() -> DealBundle:
    return DealBundle(summary=_SUMMARY, workstreams=list(_WORKSTREAMS), inbox=list(_INBOX))


def build_findings() -> list[FindingListItem]:
    return [
        FindingListItem(
            finding_id=f.finding_id,
            title=f.title,
            severity=f.severity,
            workstream=f.workstream,
            owner=f.owner,
            confidence=f.confidence,
            status=f.status,
            documents=f.documents,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in _FINDINGS
    ]


def build_finding_detail(finding_id: str) -> FindingDetail | None:
    for f in _FINDINGS:
        if f.finding_id == finding_id:
            return f
    return None


def build_security_bundle() -> SecurityBundle:
    return SecurityBundle(
        quarantined=list(_QUARANTINE),
        feed=list(_FEED),
        scorecard=list(_SCORECARD),
        total_blocked=len(_QUARANTINE),
    )
