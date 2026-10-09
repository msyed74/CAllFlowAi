"""
Post-Call Analysis Agent.

Executes deep analytical review of the complete conversation transcript immediately
after call termination. Uses gpt-4o-mini (or injected LLM callable) with structured
JSON outputs to extract:
  - BANT lead qualification score (0-100 composite + budget, authority, need, timeline)
  - Executive summary and key discussion highlights
  - Sentiment trajectory (overall & progression)
  - Pain points and objections raised
  - Recommended action items and follow-up strategy

Persists results into:
  - call_summaries (CallSummary)
  - lead_scores (LeadScore)
  - leads (updates Lead.status and custom_fields)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.calls import Call, CallSummary, CallTranscript
from backend.app.models.lead_scores import LeadScore
from backend.app.models.leads import Lead

logger = logging.getLogger("agents.post_call_analysis")


# ---------------------------------------------------------------------------
# Structured Output Pydantic Schemas
# ---------------------------------------------------------------------------

class BANTLeadScoreSchema(BaseModel):
    composite_score: int = Field(..., ge=0, le=100, description="Overall BANT score 0-100")
    budget_score: int = Field(..., ge=0, le=25, description="Budget fit 0-25")
    authority_score: int = Field(..., ge=0, le=25, description="Decision authority 0-25")
    need_score: int = Field(..., ge=0, le=25, description="Pain point urgency & solution fit 0-25")
    timeline_score: int = Field(..., ge=0, le=25, description="Purchasing timeline immediacy 0-25")
    rationale: str = Field(..., description="Evidence-backed reasoning for assigned scores")


class SentimentAnalysisSchema(BaseModel):
    overall: str = Field(..., description="Overall caller sentiment: positive | neutral | negative | frustrated")
    sentiment_trajectory: str = Field(..., description="Sentiment progression: improved | stable | deteriorated")

    @field_validator("overall")
    @classmethod
    def validate_overall(cls, v: str) -> str:
        valid = {"positive", "neutral", "negative", "frustrated"}
        return v.lower() if v.lower() in valid else "neutral"

    @field_validator("sentiment_trajectory")
    @classmethod
    def validate_trajectory(cls, v: str) -> str:
        valid = {"improved", "stable", "deteriorated"}
        return v.lower() if v.lower() in valid else "stable"


class PostCallAnalysisResult(BaseModel):
    executive_summary: str = Field(..., description="Concise 2-3 paragraph executive summary of the conversation")
    lead_score: BANTLeadScoreSchema
    pain_points: List[str] = Field(default_factory=list, description="Explicit caller pain points or bottlenecks")
    objections_raised: List[str] = Field(default_factory=list, description="Objections mentioned (e.g. price, timing, competitor)")
    sentiment_analysis: SentimentAnalysisSchema
    action_items: List[str] = Field(default_factory=list, description="Immediate action items for the sales rep")
    suggested_follow_up: str = Field(..., description="Recommended next interaction or message snippet")
    qualification_status: str = Field(default="qualified", description="qualified | unqualified | follow_up_needed | do_not_call")


# ---------------------------------------------------------------------------
# Post-Call Analysis System Prompt
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are an elite revenue operations and sales intelligence AI analyzing a completed customer phone call transcript.
Your mission is to objectively evaluate lead quality, identify key risks/objections, and score the prospect using the BANT framework:
1. Budget (0-25): Does the prospect have budget or pricing fit?
2. Authority (0-25): Is the prospect a decision-maker or influential evaluator?
3. Need (0-25): Does the prospect have a clear, pressing pain point aligned with our product?
4. Timeline (0-25): Is the prospect ready to evaluate or buy in the near future (< 3 months)?
Composite Score (0-100) = Budget + Authority + Need + Timeline.

You must return valid JSON matching this schema:
{
  "executive_summary": "string",
  "lead_score": {
    "composite_score": 0-100,
    "budget_score": 0-25,
    "authority_score": 0-25,
    "need_score": 0-25,
    "timeline_score": 0-25,
    "rationale": "string"
  },
  "pain_points": ["string"],
  "objections_raised": ["string"],
  "sentiment_analysis": {
    "overall": "positive" | "neutral" | "negative" | "frustrated",
    "sentiment_trajectory": "improved" | "stable" | "deteriorated"
  },
  "action_items": ["string"],
  "suggested_follow_up": "string",
  "qualification_status": "qualified" | "unqualified" | "follow_up_needed" | "do_not_call"
}
"""


class PostCallAnalysisAgent:
    """
    Analyzes completed call transcripts and persists intelligence summaries,
    BANT lead scoring, and qualification statuses.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_client_fn: Optional[Callable[[str, str], Coroutine[Any, Any, str]]] = None,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_SUMMARY_MODEL
        self.llm_client_fn = llm_client_fn

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Invokes OpenAI Chat Completions API with JSON mode."""
        if self.llm_client_fn:
            return await self.llm_client_fn(system_prompt, user_prompt)

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            raise RuntimeError(
                f"OpenAI Chat API error {response.status_code}: {response.text}"
            )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def analyze_call(
        self,
        call_id: str,
        db_session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Gathers call transcripts, generates structured analysis, and writes
        CallSummary and LeadScore records to the database.
        """
        # 1. Fetch Call & Transcripts
        stmt = select(Call).where(Call.id == call_id)
        call = (await db_session.execute(stmt)).scalar_one_or_none()
        if not call:
            raise ValueError(f"Call with id {call_id} not found.")

        transcripts_stmt = (
            select(CallTranscript)
            .where(CallTranscript.call_id == call_id)
            .order_by(CallTranscript.start_time_ms.asc(), CallTranscript.created_at.asc())
        )
        transcripts = (await db_session.execute(transcripts_stmt)).scalars().all()

        if not transcripts:
            logger.warning("Call %s has no transcripts. Generating minimal empty summary.", call_id)
            formatted_transcript = "[No audio turns were recorded for this call.]"
        else:
            turns = []
            for t in transcripts:
                prefix = "Lead" if t.speaker_role == "user" else "Assistant"
                turns.append(f"{prefix}: {t.content}")
            formatted_transcript = "\n".join(turns)

        # 2. Invoke LLM for Intelligence Extraction
        user_prompt = f"""Analyze the following telephone call transcript:

Call Details:
- Call ID: {call.id}
- Direction: {call.direction}
- From: {call.from_number}
- To: {call.to_number}

Transcript:
{formatted_transcript}
"""

        try:
            raw_response_text = await self._call_llm(ANALYSIS_SYSTEM_PROMPT, user_prompt)
            parsed_json = json.loads(raw_response_text)
            analysis = PostCallAnalysisResult.model_validate(parsed_json)
        except Exception as e:
            logger.error("Failed to parse LLM analysis for call %s: %s", call_id, e)
            # Resilient fallback
            analysis = PostCallAnalysisResult(
                executive_summary="Analysis generation encountered an error or call transcript was insufficient.",
                lead_score=BANTLeadScoreSchema(
                    composite_score=50,
                    budget_score=12,
                    authority_score=12,
                    need_score=13,
                    timeline_score=13,
                    rationale="Default score due to processing fallback.",
                ),
                pain_points=[],
                objections_raised=[],
                sentiment_analysis=SentimentAnalysisSchema(
                    overall="neutral",
                    sentiment_trajectory="stable",
                ),
                action_items=["Review call audio manually"],
                suggested_follow_up="Follow up with prospect via email or phone call.",
                qualification_status="follow_up_needed",
            )
            parsed_json = analysis.model_dump()

        # 3. Upsert CallSummary
        existing_summary_stmt = select(CallSummary).where(CallSummary.call_id == call_id)
        call_summary = (await db_session.execute(existing_summary_stmt)).scalar_one_or_none()

        if not call_summary:
            call_summary = CallSummary(
                id=str(uuid.uuid4()),
                call_id=call_id,
                organization_id=call.organization_id,
                executive_summary=analysis.executive_summary,
                sentiment_overall=analysis.sentiment_analysis.overall,
                primary_intent=analysis.qualification_status,
                qualification_status=analysis.qualification_status,
                pain_points=analysis.pain_points,
                objections_raised=analysis.objections_raised,
                action_items=analysis.action_items,
                recommended_follow_up=analysis.suggested_follow_up,
                raw_llm_response=parsed_json,
                generated_at=datetime.now(timezone.utc),
            )
            db_session.add(call_summary)
        else:
            call_summary.executive_summary = analysis.executive_summary
            call_summary.sentiment_overall = analysis.sentiment_analysis.overall
            call_summary.primary_intent = analysis.qualification_status
            call_summary.qualification_status = analysis.qualification_status
            call_summary.pain_points = analysis.pain_points
            call_summary.objections_raised = analysis.objections_raised
            call_summary.action_items = analysis.action_items
            call_summary.recommended_follow_up = analysis.suggested_follow_up
            call_summary.raw_llm_response = parsed_json

        # 4. Upsert LeadScore if lead_id is present
        lead_score_rec = None
        if call.lead_id:
            lead_score_rec = LeadScore(
                id=str(uuid.uuid4()),
                call_id=call_id,
                lead_id=call.lead_id,
                organization_id=call.organization_id,
                composite_score=analysis.lead_score.composite_score,
                budget_score=analysis.lead_score.budget_score,
                authority_score=analysis.lead_score.authority_score,
                need_score=analysis.lead_score.need_score,
                timeline_score=analysis.lead_score.timeline_score,
                score_breakdown={
                    "budget": analysis.lead_score.budget_score,
                    "authority": analysis.lead_score.authority_score,
                    "need": analysis.lead_score.need_score,
                    "timeline": analysis.lead_score.timeline_score,
                    "trajectory": analysis.sentiment_analysis.sentiment_trajectory,
                },
                reasoning=analysis.lead_score.rationale,
                created_at=datetime.now(timezone.utc),
            )
            db_session.add(lead_score_rec)

            # Also update Lead record with latest score and status
            lead_stmt = select(Lead).where(Lead.id == call.lead_id)
            lead = (await db_session.execute(lead_stmt)).scalar_one_or_none()
            if lead:
                if analysis.qualification_status in ("qualified", "unqualified", "do_not_call"):
                    lead.status = "qualified" if analysis.qualification_status == "qualified" else ("do_not_contact" if analysis.qualification_status == "do_not_call" else "unqualified")
                lead_custom = dict(lead.custom_fields or {})
                lead_custom["latest_lead_score"] = analysis.lead_score.composite_score
                lead_custom["qualification_status"] = analysis.qualification_status
                lead.custom_fields = lead_custom

        await db_session.commit()
        logger.info(
            "Call %s analysis complete: score=%d, sentiment=%s, status=%s",
            call_id,
            analysis.lead_score.composite_score,
            analysis.sentiment_analysis.overall,
            analysis.qualification_status,
        )

        return {
            "call_id": call_id,
            "organization_id": call.organization_id,
            "lead_id": call.lead_id,
            "summary_id": call_summary.id,
            "lead_score_id": lead_score_rec.id if lead_score_rec else None,
            "analysis": analysis.model_dump(),
        }
