import { coaEligibility, coaErrorMessage } from "../lib/coaEligibility";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import SampleDetail from "@/pages/SampleDetail";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  apiError: jest.fn((detail) => (typeof detail === "string" ? detail : "Request failed")),
}));

jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useParams: () => ({ id: "sample-1" }),
}));

const renderSample = (qaStatus) => {
  const sample = {
    id: "sample-1",
    sample_point_id: "point-1",
    sample_point_name: "Point A",
    record_id: "REC-1",
    sample_date: "2026-09-08",
    analyst_initials: "QC",
    status: "COMPLETE",
    overall_result: "PASS",
    qa_status: qaStatus,
    results: [],
    instrument_issues: [],
  };
  api.get.mockImplementation((path) => {
    const data = {
      "/samples/sample-1": sample,
      "/specifications": [],
      "/parameters": [],
      "/audit-trail": [],
      "/instruments": [],
    }[path];
    return Promise.resolve({ data });
  });
  useAuth.mockReturnValue({
    user: { role: "qc" },
    can: (...roles) => roles.includes("qc"),
  });

  return render(
    <MemoryRouter>
      <SampleDetail />
    </MemoryRouter>,
  );
};

describe("sample CoA eligibility", () => {
  const approvedSample = { qa_status: "Approved" };

  it("blocks ordinary CoA while required results are outstanding", () => {
    expect(coaEligibility(approvedSample, true, ["COD", "Ammonia"])).toEqual({
      eligible: false,
      message: "CoA is unavailable until required results are entered: COD, Ammonia.",
    });
  });

  it("blocks CoA until the complete record has QA approval", () => {
    expect(coaEligibility({ qa_status: "Pending Review" }, false, [])).toEqual({
      eligible: false,
      message: "CoA is unavailable until QA approves this complete record.",
    });
  });

  it("allows CoA for a complete QA-approved record", () => {
    expect(coaEligibility(approvedSample, false, [])).toEqual({
      eligible: true,
      message: "",
    });
  });

  it("blocks CoA when required instrument traceability is invalid", () => {
    expect(
      coaEligibility(approvedSample, false, [], [
        { parameter: "Methanol", reason: "A registered GC instrument is required." },
      ]),
    ).toEqual({
      eligible: false,
      message:
        "CoA is unavailable until instrument traceability is corrected. " +
        "Methanol: A registered GC instrument is required.",
    });
  });

  it("formats an unexpected 422 response for a controlled toast", () => {
    expect(
      coaErrorMessage({
        message: "Cannot issue an ordinary CoA: required results are missing",
        outstanding_parameters: ["COD", "Ammonia"],
      }),
    ).toBe("Cannot issue an ordinary CoA: required results are missing: COD, Ammonia.");
  });
});

describe("SampleDetail submission action", () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
    useAuth.mockReset();
    toast.error.mockReset();
    toast.success.mockReset();
  });

  it.each(["Pending Review", "Approved"])(
    "does not offer QA submission when status is %s",
    async (qaStatus) => {
      renderSample(qaStatus);
      expect(await screen.findByTestId("sample-detail-page")).toBeInTheDocument();
      expect(screen.queryByTestId("submit-review-btn")).not.toBeInTheDocument();
    },
  );

  it("handles a 409 response without retrying the submission", async () => {
    renderSample("Not Submitted");
    const submitButton = await screen.findByTestId("submit-review-btn");
    api.post.mockRejectedValueOnce({
      response: { status: 409, data: { detail: "Sample is no longer eligible for submission." } },
    });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Sample state changed. Reload before submitting for QA review.",
      );
      expect(api.post).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByTestId("sample-detail-page")).toBeInTheDocument();
  });
});