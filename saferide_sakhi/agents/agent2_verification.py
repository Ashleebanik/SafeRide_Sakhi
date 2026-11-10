"""Agent 2 – Chauffeur Verification & Matching Agent
Checks ID, police verification and licence status, matches a nearby
woman chauffeur, and confirms face-match before trip start.
Rule-based; no LLM required.
"""
from __future__ import annotations

from typing import Any

from saferide_sakhi.logger import AgentLogger, Timer
from saferide_sakhi.models import ChauffeurProfile, GPSPoint, VerificationStatus
from saferide_sakhi.mcp_tools.tools import haversine_m, verify_chauffeur

_log = AgentLogger("ChauffeurVerificationAgent")


def run(
    chauffeur: ChauffeurProfile,
    rider_location: GPSPoint,
    max_distance_km: float = 5.0,
) -> dict[str, Any]:
    """
    Verify a chauffeur and decide if she can be matched to this trip.

    Returns:
        {
            "approved": bool,
            "issues": list[str],
            "distance_km": float,
            "recommendation": str
        }
    """
    record = chauffeur.model_dump(mode="json")

    with Timer() as t:
        result = verify_chauffeur(record)

        # Distance check
        distance_km = 99.0
        if chauffeur.current_location:
            distance_km = round(
                haversine_m(
                    rider_location.lat, rider_location.lon,
                    chauffeur.current_location.lat, chauffeur.current_location.lon,
                ) / 1000,
                2,
            )

        too_far = distance_km > max_distance_km
        if too_far:
            result["issues"].append(f"chauffeur_too_far_{distance_km}km")

        approved = result["passed"] and not too_far

        if approved:
            recommendation = "Assign chauffeur – all checks passed."
        elif result["issues"]:
            recommendation = f"Do NOT assign – issues: {', '.join(result['issues'])}"
        else:
            recommendation = "Assign with caution – distance borderline."

    _log.step(
        trip_id="pre-trip",
        stage="chauffeur_verification",
        input_summary=f"chauffeur={chauffeur.name}, dist={distance_km}km",
        tool_call="verify_chauffeur",
        output_summary=f"approved={approved}, issues={result['issues']}",
        latency_ms=t.elapsed_ms,
        decision=recommendation,
    )

    return {
        "approved": approved,
        "issues": result["issues"],
        "distance_km": distance_km,
        "recommendation": recommendation,
    }
