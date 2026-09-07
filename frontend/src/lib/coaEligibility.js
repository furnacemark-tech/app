export function coaEligibility(sample, incomplete, outstandingParams) {
  if (incomplete) {
    const parameters = outstandingParams.join(", ");
    return {
      eligible: false,
      message: parameters
        ? `CoA is unavailable until required results are entered: ${parameters}.`
        : "CoA is unavailable until all required results are entered.",
    };
  }

  if (sample.qa_status !== "Approved") {
    return {
      eligible: false,
      message: "CoA is unavailable until QA approves this complete record.",
    };
  }

  return {
    eligible: true,
    message: "",
  };
}

export function coaErrorMessage(detail) {
  if (detail && typeof detail === "object" && detail.message) {
    const outstanding = Array.isArray(detail.outstanding_parameters)
      ? detail.outstanding_parameters.filter(Boolean)
      : [];
    if (outstanding.length > 0) {
      return `${detail.message}: ${outstanding.join(", ")}.`;
    }
    return detail.message;
  }

  if (detail == null) {
    return "Something went wrong. Please try again.";
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((entry) => (entry && typeof entry.msg === "string" ? entry.msg : JSON.stringify(entry)))
      .join(" ");
  }

  if (detail && typeof detail.msg === "string") {
    return detail.msg;
  }

  return String(detail);
}