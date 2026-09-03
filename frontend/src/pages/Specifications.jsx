import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function numericOrExisting(draftValue, existing) {
  if (draftValue === undefined) return existing;
  return draftValue === "" ? null : parseFloat(draftValue);
}

export default function Specifications() {  const { can } = useAuth();
  const [points, setPoints] = useState([]);
  const [params, setParams] = useState([]);
  const [pointId, setPointId] = useState("");
  const [specs, setSpecs] = useState([]);
  const [draft, setDraft] = useState({});

  useEffect(() => {
    Promise.all([api.get("/sample-points"), api.get("/parameters")]).then(([sp, pr]) => {
      setPoints(sp.data);
      setParams(pr.data);
      setPointId(sp.data[0]?.id || "");
    });
  }, []);

  const load = useCallback(
    (id) => api.get("/specifications", { params: { sample_point_id: id } }).then(({ data }) => setSpecs(data)),
    []
  );

  useEffect(() => {
    if (pointId) load(pointId);
  }, [pointId, load]);

  const paramById = Object.fromEntries(params.map((p) => [p.id, p]));
  const editable = can("admin", "qa");

  const save = async (s) => {
    const d = draft[s.id] || {};
    try {
      await api.put(`/specifications/${s.id}`, {
        sample_point_id: s.sample_point_id,
        parameter_id: s.parameter_id,
        lower_limit: numericOrExisting(d.lower_limit, s.lower_limit),
        upper_limit: numericOrExisting(d.upper_limit, s.upper_limit),
        expected_text: d.expected_text !== undefined ? d.expected_text : s.expected_text,
        active: true,
      });
      toast.success("Specification updated (new version recorded)");
      load(pointId);
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="specifications-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Specification Limits</h1>
        <p className="text-sm text-slate-600 mt-1">
          {editable ? "Controlled limits — every change is versioned and audited." : "Read-only for QC role."}
        </p>
      </div>

      <select
        data-testid="spec-point-select"
        className="border border-slate-300 rounded px-3 py-2 text-sm bg-white max-w-xs"
        value={pointId}
        onChange={(e) => setPointId(e.target.value)}
      >
        {points.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Parameter</TableHead>
              <TableHead>Units</TableHead>
              <TableHead>Lower</TableHead>
              <TableHead>Upper</TableHead>
              <TableHead>Expected text</TableHead>
              <TableHead>Version</TableHead>
              {editable && <TableHead></TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody data-testid="specs-table-body">
            {specs.map((s) => {
              const p = paramById[s.parameter_id];
              const d = draft[s.id] || {};
              return (
                <TableRow key={s.id} data-testid={`spec-row-${p?.name?.replace(/\s+/g, "-").toLowerCase()}`}>
                  <TableCell className="font-medium">{p?.name}</TableCell>
                  <TableCell className="text-slate-500 text-xs">{p?.units}</TableCell>
                  <TableCell>
                    {editable && p?.value_type === "numeric" ? (
                      <Input
                        className="h-8 w-24 tabnum"
                        type="number"
                        step="any"
                        data-testid={`spec-lower-${p?.name?.replace(/\s+/g, "-").toLowerCase()}`}
                        value={d.lower_limit !== undefined ? d.lower_limit : s.lower_limit ?? ""}
                        onChange={(e) => setDraft({ ...draft, [s.id]: { ...d, lower_limit: e.target.value } })}
                      />
                    ) : (
                      <span className="tabnum">{s.lower_limit ?? "–"}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {editable && p?.value_type === "numeric" ? (
                      <Input
                        className="h-8 w-24 tabnum"
                        type="number"
                        step="any"
                        data-testid={`spec-upper-${p?.name?.replace(/\s+/g, "-").toLowerCase()}`}
                        value={d.upper_limit !== undefined ? d.upper_limit : s.upper_limit ?? ""}
                        onChange={(e) => setDraft({ ...draft, [s.id]: { ...d, upper_limit: e.target.value } })}
                      />
                    ) : (
                      <span className="tabnum">{s.upper_limit ?? "–"}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {editable && p?.value_type !== "numeric" ? (
                      <Input
                        className="h-8 w-44"
                        data-testid={`spec-expected-${p?.name?.replace(/\s+/g, "-").toLowerCase()}`}
                        value={d.expected_text !== undefined ? d.expected_text : s.expected_text ?? ""}
                        onChange={(e) => setDraft({ ...draft, [s.id]: { ...d, expected_text: e.target.value } })}
                      />
                    ) : (
                      s.expected_text || "–"
                    )}
                  </TableCell>
                  <TableCell className="tabnum text-xs">v{s.version}</TableCell>
                  {editable && (
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid={`spec-save-${p?.name?.replace(/\s+/g, "-").toLowerCase()}`}
                        onClick={() => save(s)}
                      >
                        Save
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
