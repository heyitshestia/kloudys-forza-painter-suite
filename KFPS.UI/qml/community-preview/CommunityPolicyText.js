.pragma library

function contribution(state, ui) {
    switch (state) {
    case "not_claimed": return ui("Authorship not claimed", "원작자 확인 전")
    case "permission_only": return ui("Shared with permission", "공유 허가를 받은 작품")
    case "pending_publication": return ui("Awaiting publication", "게시 대기 중")
    case "scheduled": return ui("Credit after publication starts", "공개 시작 후 기여 인정")
    case "credited": return ui("Contribution credited", "기여 인정 완료")
    case "revoked": return ui("Contribution revoked", "기여 인정 취소")
    case "duplicate": return ui("Duplicate contribution", "중복 기여")
    case "review_required": return ui("Staff review required", "운영진 검토 필요")
    case "not_eligible": return ui("Not eligible for contribution credit", "기여 인정 대상 아님")
    default: return ui("Contribution status unavailable", "기여 상태 확인 불가")
    }
}

function claimError(code, ui) {
    switch (code) {
    case "artwork_not_found": return ui("Upload not found", "업로드를 찾을 수 없음")
    case "claim_revision_changed": return ui("Revision changed. Refresh and select again.", "수정본이 변경되었습니다. 새로고침 후 다시 선택하세요.")
    case "credit_revoked": return ui("Credit was revoked. Contact staff for review.", "기여 인정이 취소되었습니다. 운영진에게 검토를 요청하세요.")
    case "duplicate_contribution": return ui("This vinyl already has contribution credit.", "이미 기여로 인정된 비닐입니다.")
    case "claim_evidence_required": return ui("Staff review is needed for this upload.", "이 업로드는 운영진 검토가 필요합니다.")
    case "vinyl_required": return ui("Only original vinyls count, not liveries.", "원본 비닐만 인정되며 리버리는 제외됩니다.")
    case "handmade_required": return ui("Only original Handmade vinyls count. Toolmade uploads do not earn credit.", "원본 수작업 비닐만 인정됩니다. 도구 제작 작품은 기여로 계산되지 않습니다.")
    default: return ui("The claim could not be verified.", "원작자 확인 요청을 검증하지 못했습니다.")
    }
}

function claimRequestError(code, ui) {
    switch (code) {
    case "access_changed": return ui("Your account access changed. Refresh your uploads and review the selection again.", "계정 접근 권한이 변경되었습니다. 업로드를 새로고침하고 선택 항목을 다시 검토하세요.")
    case "rate_limited": return ui("Too many claim requests. Wait before trying again.", "확인 요청이 너무 많습니다. 잠시 후 다시 시도하세요.")
    case "invalid_claim_response": return ui("The claim results could not be verified. Refresh your uploads before trying again.", "확인 요청 결과를 검증하지 못했습니다. 업로드를 새로고침한 후 다시 시도하세요.")
    default: return ui("Claims could not be submitted. Refresh your account and uploads before trying again.", "확인 요청을 제출하지 못했습니다. 계정과 업로드를 새로고침한 후 다시 시도하세요.")
    }
}
