"""
Laya-based risk assessment module for NER-LENS.

This module provides a local/self-hosted risk assessment using the
convaiinnovations/laya model from Hugging Face.
"""

import os
import logging
from typing import Dict, Any, Optional
import laya

logger = logging.getLogger(__name__)

# Label mapping for risk levels
RISK_LEVELS = ["low", "caution", "high"]

# Singleton agent holder
_agent = None


def _get_agent():
    """Load the Laya agent from Hugging Face."""
    global _agent
    if _agent is not None:
        return _agent

    model_name = "convaiinnovations/laya"
    logger.info(f"Loading Laya agent: {model_name}")
    try:
        _agent = laya.load(
            model_name,
            subfolder="typed-decisions",
            fast=False,
        )
        logger.info("Laya agent loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load Laya agent: {e}")
        raise
    return _agent


def _format_evidence_state(
    impact: Dict[str, Any],
    route: Dict[str, Any],
    segments: Dict[str, Any],
) -> Dict[str, str]:
    """Format the input evidence into a state dict for the Laya agent.

    Args:
        impact: Mission impact data
        route: Route candidate data
        segments: Segment status data

    Returns:
        State dict with string values for placeholders in questions.
    """
    # Extract relevant data from impact
    payload = impact.get("payload", {})
    impact_segment_id = str(payload.get("segment_id", ""))
    impact_status = str(payload.get("status", ""))
    impact_decision_evidence_ids = ", ".join(
        map(str, payload.get("decision_evidence_ids", []))
    )
    impact_assessment_basis = str(payload.get("assessment_basis", ""))

    # Extract route data
    route_id = str(route.get("route_id", ""))
    route_distance_m = str(route.get("distance_m", ""))
    route_duration_s = str(route.get("duration_seconds", {}).get("p50", ""))
    route_segment_ids = ", ".join(map(str, route.get("segment_ids", [])))

    # Extract segment statuses
    segment_details = []
    for seg_id in route.get("segment_ids", []):
        seg_status = segments.get(seg_id, {})
        segment_details.append(
            f"Segment {seg_id}: Status={seg_status.get('status', 'unknown')}, "
            f"Freshness={seg_status.get('freshness', 'unknown')}, "
            f"Vehicle Scope={seg_status.get('vehicle_scope', 'unknown')}"
        )
    segment_details_str = "; ".join(segment_details)

    # Build state dict
    state = {
        "impact_segment_id": impact_segment_id,
        "impact_status": impact_status,
        "impact_decision_evidence_ids": impact_decision_evidence_ids,
        "impact_assessment_basis": impact_assessment_basis,
        "route_id": route_id,
        "route_distance_m": route_distance_m,
        "route_duration_s": route_duration_s,
        "route_segment_ids": route_segment_ids,
        "segment_details": segment_details_str,
    }
    return state


def _parse_model_output(predict_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse the agent's predict output into risk level and probability.

    Args:
        predict_result: Output from agent.predict

    Returns:
        Parsed dictionary with keys: risk_level, probability
        or None if parsing fails
    """
    try:
        answers = predict_result.get("answers", {})
        risk_level_answer = answers.get("risk_level", {})
        probability_answer = answers.get("probability", {})

        risk_level = risk_level_answer.get("choice")
        probability = probability_answer.get("score")

        if risk_level is None or probability is None:
            logger.warning("Missing risk_level or probability in Laya output")
            return None

        # Validate risk_level
        if risk_level not in RISK_LEVELS:
            logger.warning(f"Invalid risk_level: {risk_level}")
            return None

        # Validate probability (should be float between 0 and 1)
        prob = float(probability)
        if not (0.0 <= prob <= 1.0):
            logger.warning(f"Probability out of range: {prob}")
            return None

        return {"risk_level": risk_level, "probability": prob}
    except (ValueError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to parse Laya predict output: {e}")
        return None


def _insufficient_evidence(reason: str) -> Dict[str, Any]:
    """Return an insufficient evidence response.

    Args:
        reason: Explanation of why evidence is insufficient

    Returns:
        Dictionary with state="insufficient_evidence" and appropriate fields.
    """
    return {
        "state": "insufficient_evidence",
        "probability_weighted_minutes": None,
        "risk": None,
        "source": "abstention",
        "explanation": f"Insufficient evidence: {reason}",
    }


def assess_risk(
    impact: Dict[str, Any],
    route: Dict[str, Any],
    segments: Dict[str, Any],
) -> Dict[str, Any]:
    """Assess risk using the Laya model.

    Args:
        impact: Mission impact data
        route: Route candidate data
        segments: Segment status data (mapping segment_id to status dict)

    Returns:
        Dictionary with keys:
            - state: risk state string (one of "insufficient_evidence", "low", "caution", "high")
            - probability_weighted_minutes: float or None
            - risk: float between 0 and 1 or None (for score_components.risk)
            - source: "laya", "abstention", or "fallback"
            - explanation: string (for logging, not included in final output)
    """
    # Abstention logic: check for missing or stale critical evidence
    if impact is None:
        return _insufficient_evidence("Impact is missing")
    payload = impact.get("payload")
    if payload is None:
        return _insufficient_evidence("Impact payload is missing")
    segment_id = payload.get("segment_id")
    status = payload.get("status")
    if segment_id is None:
        return _insufficient_evidence("Impact segment_id is missing")
    if status is None:
        return _insufficient_evidence("Impact status is missing")
    if not route.get("segment_ids"):
        return _insufficient_evidence("Route has no segment IDs")
    for seg_id in route.get("segment_ids", []):
        if seg_id not in segments:
            return _insufficient_evidence(f"Segment {seg_id} status is missing")
        seg_status = segments[seg_id].get("status")
        if seg_status is None or seg_status == "unknown":
            return _insufficient_evidence(f"Segment {seg_id} has unknown or missing status")

    # Use Laya model (active for this delivery)
    try:
        agent = _get_agent()
        state = _format_evidence_state(impact, route, segments)

        # Define questions for risk assessment
        questions = {
            "risk_level": {
                "type": "choice",
                "instructions": "What is the risk level?",
                "criteria": {
                    "low": "low risk",
                    "caution": "caution",
                    "high": "high risk",
                },
            },
            "probability": {
                "type": "score",
                "instructions": "What is the probability of risk occurrence (0.0 to 1.0)?",
                "criteria": ["0.0 (no risk)", "1.0 (certain risk)"],
            },
        }

        predict_result = agent.predict(state=state, questions=questions)
        logger.debug(f"Laya predict result: {predict_result}")

        parsed = _parse_model_output(predict_result)
        if parsed is None:
            logger.warning("Failed to parse Laya predict output, using fallback")
            return _fallback_assessment(impact, route, segments)

        risk_level = parsed["risk_level"]
        probability = parsed["probability"]

        # Calculate probability_weighted_minutes (6 hours = 21600 seconds = 360 minutes)
        probability_weighted_minutes = probability * 360.0

        return {
            "state": risk_level,
            "probability_weighted_minutes": probability_weighted_minutes,
            "risk": probability,
            "source": "laya",
            "explanation": f"Laya assessment: {risk_level} risk with probability {probability:.2f}",
        }

    except Exception as e:
        logger.error(f"Error during Laya risk assessment: {e}")
        return _fallback_assessment(impact, route, segments)


def _fallback_assessment(impact: Dict[str, Any], route: Dict[str, Any],
                         segments: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback risk assessment.

    Args:
        impact: Mission impact data
        route: Route candidate data
        segments: Segment status data

    Returns:
        Dictionary with the same structure as assess_risk, but with source="fallback"
    """
    logger.info("Using fallback risk assessment")

    # Simple heuristic: if any segment is closed or restricted, assign high risk
    # Otherwise, assign low risk
    has_closed_or_restricted = False
    for seg_id in route.get("segment_ids", []):
        seg_status = segments.get(seg_id, {})
        if seg_status.get("status") in ["closed", "restricted"]:
            has_closed_or_restricted = True
            break

    if has_closed_or_restricted:
        risk_level = "high"
        probability = 0.8
    else:
        risk_level = "low"
        probability = 0.2

    probability_weighted_minutes = probability * 360.0

    return {
        "state": risk_level,
        "probability_weighted_minutes": probability_weighted_minutes,
        "risk": probability,
        "source": "fallback",
        "explanation": "Fallback rule-based assessment: high risk if any segment is closed/restricted, otherwise low risk.",
    }