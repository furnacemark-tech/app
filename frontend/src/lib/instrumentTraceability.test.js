import {
  eligibleInstruments,
  traceabilityErrorMessage,
  traceabilityIssueSummary,
} from "./instrumentTraceability";

describe("sample instrument traceability helpers", () => {
  const parameter = {
    instrument_required: true,
    instrument_category: "PH_METER",
  };
  const instruments = [
    {
      id: "ph-ready",
      active: true,
      category: "PH_METER",
      in_calibration: true,
      in_service: true,
      availability_status: "AVAILABLE",
    },
    {
      id: "ph-overdue",
      active: true,
      category: "PH_METER",
      in_calibration: false,
      in_service: true,
      availability_status: "AVAILABLE",
    },
    {
      id: "hplc-ready",
      active: true,
      category: "HPLC",
      in_calibration: true,
      in_service: true,
      availability_status: "AVAILABLE",
    },
  ];

  it("offers only eligible instruments in the required category", () => {
    expect(eligibleInstruments(parameter, instruments).map((instrument) => instrument.id)).toEqual([
      "ph-ready",
    ]);
  });

  it("offers no instrument choice for a manual parameter", () => {
    expect(eligibleInstruments({ instrument_required: false }, instruments)).toEqual([]);
  });

  it("formats backend traceability issues for a controlled message", () => {
    const issues = [{ parameter: "Methanol", reason: "A registered GC instrument is required." }];
    expect(traceabilityIssueSummary(issues)).toBe(
      "Methanol: A registered GC instrument is required.",
    );
    expect(
      traceabilityErrorMessage({
        message: "Cannot save results: instrument traceability is invalid.",
        instrument_issues: issues,
      }),
    ).toBe(
      "Cannot save results: instrument traceability is invalid. " +
        "Methanol: A registered GC instrument is required.",
    );
  });
});