import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import api from "@/lib/api";
import QAQueues from "@/pages/QAQueues";

jest.mock("@/lib/api", () => ({ __esModule: true, default: { get: jest.fn() } }));

const payload = (over = {}) => ({
  items: [],
  page: 1,
  page_size: 25,
  total_items: 0,
  total_pages: 1,
  has_previous: false,
  has_next: false,
  category_counts: { ready: 0, blocked: 0, oos: 0, instrument_issue: 0, approved: 0, returned: 0 },
  total_attention_records: 0,
  samples_pending_review: 0,
  awaiting_review: [],
  on_hold: [],
  certificates_to_send: [],
  reissue_required: [],
  ...over,
});

// Axios resolves to a response envelope; the component reads `.data`.
const resp = (over = {}) => ({ data: payload(over) });

const row = (recordId, over = {}) => ({
  id: `id-${recordId}`,
  record_id: recordId,
  sample_point_name: "Point A",
  sample_date: "2026-09-08",
  analyst_initials: "MF",
  status: "COMPLETE",
  qa_status: "Pending Review",
  overall_result: "PASS",
  attention_reasons: [],
  ...over,
});

const renderPage = () => render(<MemoryRouter><QAQueues /></MemoryRouter>);
const lastParams = () => api.get.mock.calls.at(-1)[1].params;

beforeEach(() => {
  api.get.mockReset();
});

describe("QAQueues component", () => {
  it("shows a loading state before the first response arrives", () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId("qa-queues-loading")).toBeInTheDocument();
  });

  it("renders returned records and the total-items count", async () => {
    api.get.mockResolvedValue(
      resp({
        items: [row("REC-1"), row("REC-2")],
        total_items: 2,
        total_attention_records: 2,
        category_counts: { ready: 2, blocked: 0, oos: 0, instrument_issue: 0, approved: 0, returned: 0 },
      }),
    );
    renderPage();
    expect(await screen.findByTestId("sample-qa-queue-row-REC-1")).toBeInTheDocument();
    expect(screen.getByTestId("sample-qa-queue-row-REC-2")).toBeInTheDocument();
    expect(screen.getByTestId("sample-qa-total-items")).toHaveTextContent("2 record(s)");
  });

  it("shows the empty state when the category has no records", async () => {
    api.get.mockResolvedValue(resp());
    renderPage();
    expect(await screen.findByTestId("sample-qa-empty-state")).toBeInTheDocument();
  });

  it("switches category and resets to page 1 when a filter is clicked", async () => {
    api.get.mockResolvedValue(
      resp({ items: [row("REC-1")], total_items: 1, total_pages: 2, has_next: true }),
    );
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");

    fireEvent.click(screen.getByTestId("sample-qa-next-button")); // move to page 2
    await waitFor(() => expect(lastParams().page).toBe(2));

    fireEvent.click(screen.getByTestId("sample-qa-filter-oos")); // change category
    await waitFor(() => {
      const params = lastParams();
      expect(params.category).toBe("oos");
      expect(params.page).toBe(1);
    });
  });

  it("resets to page 1 and sends trimmed search text on search", async () => {
    api.get.mockResolvedValue(
      resp({ items: [row("REC-1")], total_items: 1, total_pages: 3, has_next: true }),
    );
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");

    fireEvent.click(screen.getByTestId("sample-qa-next-button")); // page 2
    await waitFor(() => expect(lastParams().page).toBe(2));

    fireEvent.change(screen.getByTestId("sample-qa-search-input"), {
      target: { value: "  REC-9  " },
    });
    await waitFor(() => {
      const params = lastParams();
      expect(params.page).toBe(1);
      expect(params.search).toBe("REC-9");
    });
  });

  it("omits the search parameter when the box is blank", async () => {
    api.get.mockResolvedValue(resp({ items: [row("REC-1")], total_items: 1 }));
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");
    fireEvent.change(screen.getByTestId("sample-qa-search-input"), { target: { value: "   " } });
    await waitFor(() => expect("search" in lastParams()).toBe(false));
  });

  it("disables Previous on the first page and Next on the last page", async () => {
    api.get.mockResolvedValue(
      resp({ items: [row("REC-1")], total_items: 1, total_pages: 1, has_previous: false, has_next: false }),
    );
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");
    expect(screen.getByTestId("sample-qa-previous-button")).toBeDisabled();
    expect(screen.getByTestId("sample-qa-next-button")).toBeDisabled();
    expect(screen.getByTestId("sample-qa-pagination-label")).toHaveTextContent("Page 1 of 1");
  });

  it("advances the page when Next is clicked at a mid-range boundary", async () => {
    api.get.mockResolvedValue(
      resp({ items: [row("REC-1")], total_items: 60, total_pages: 3, has_previous: false, has_next: true }),
    );
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");
    const next = screen.getByTestId("sample-qa-next-button");
    expect(next).toBeEnabled();
    fireEvent.click(next);
    await waitFor(() => expect(lastParams().page).toBe(2));
  });

  it("shows a controlled error message when the first load fails", async () => {
    api.get.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByTestId("qa-queues-api-error")).toHaveTextContent(
      /Unable to load the QA attention queue/i,
    );
  });

  it("keeps prior data and shows an inline error when a later request fails", async () => {
    api.get.mockResolvedValueOnce(
      resp({ items: [row("REC-1")], total_items: 1, total_pages: 2, has_next: true }),
    );
    renderPage();
    await screen.findByTestId("sample-qa-queue-row-REC-1");

    api.get.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByTestId("sample-qa-next-button"));

    expect(await screen.findByTestId("sample-qa-api-error")).toBeInTheDocument();
    expect(screen.getByTestId("sample-qa-queue-row-REC-1")).toBeInTheDocument();
  });

  it("ignores a stale response that resolves after a newer one (out-of-order)", async () => {
    const resolvers = [];
    api.get.mockImplementation(() => new Promise((resolve) => resolvers.push(resolve)));

    renderPage(); // request #0 (initial)
    await waitFor(() => expect(resolvers.length).toBe(1));
    await act(async () => resolvers[0](resp({ items: [row("REC-INIT")], total_items: 1 })));
    await screen.findByTestId("sample-qa-queue-row-REC-INIT");

    // Two rapid searches → requests #1 then #2 (latest is #2).
    fireEvent.change(screen.getByTestId("sample-qa-search-input"), { target: { value: "A" } });
    await waitFor(() => expect(resolvers.length).toBe(2));
    fireEvent.change(screen.getByTestId("sample-qa-search-input"), { target: { value: "AB" } });
    await waitFor(() => expect(resolvers.length).toBe(3));

    // Resolve the NEWER request (#2) first.
    await act(async () => resolvers[2](resp({ items: [row("REC-NEW")], total_items: 1 })));
    await screen.findByTestId("sample-qa-queue-row-REC-NEW");

    // Then resolve the older, now-stale request (#1) — it must be ignored.
    await act(async () => resolvers[1](resp({ items: [row("REC-OLD")], total_items: 1 })));
    await waitFor(() =>
      expect(screen.queryByTestId("sample-qa-queue-row-REC-OLD")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("sample-qa-queue-row-REC-NEW")).toBeInTheDocument();
  });
});
