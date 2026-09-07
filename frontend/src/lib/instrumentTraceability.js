export function eligibleInstruments(parameter, instruments) {
  if (!parameter.instrument_required) {
    return [];
  }

  return instruments.filter(
    (instrument) =>
      instrument.active &&
      instrument.category === parameter.instrument_category &&
      instrument.in_calibration &&
      instrument.in_service &&
      instrument.availability_status === "AVAILABLE",
  );
}

export function traceabilityIssueSummary(issues = []) {
  return issues.map((issue) => `${issue.parameter}: ${issue.reason}`).join("; ");
}

export function traceabilityErrorMessage(detail) {
  if (detail && typeof detail === "object" && detail.message) {
    const issues = traceabilityIssueSummary(detail.instrument_issues);
    return issues ? `${detail.message} ${issues}` : detail.message;
  }
  return "Unable to validate instrument traceability. Please try again.";
}