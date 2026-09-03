import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";

const entriesFromResults = (results = []) => {
  const map = {};
  results.forEach((r) => {
    const numeric = r.value_numeric !== null && r.value_numeric !== undefined;
    map[r.parameter_id] = { value: numeric ? String(r.value_numeric) : r.value_text || "", reason: "" };
  });
  return map;
};

export function useBatch(id) {
  const [batch, setBatch] = useState(null);
  const [params, setParams] = useState([]);
  const [instruments, setInstruments] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [entries, setEntries] = useState({});
  const [instrumentId, setInstrumentId] = useState("");
  const [productionDate, setProductionDate] = useState("");

  const load = useCallback(async () => {
    const { data } = await api.get(`/batches/${id}`);
    setBatch(data);
    setInstrumentId(data.instrument_id || "");
    setProductionDate(data.production_date);
    setEntries(entriesFromResults(data.results));
  }, [id]);

  useEffect(() => {
    load();
    api.get("/parameters").then(({ data }) => setParams(data));
    api.get("/instruments").then(({ data }) => setInstruments(data));
    api.get("/customers").then(({ data }) => setCustomers(data));
  }, [load]);

  const call = useCallback(
    async (request, okMsg) => {
      try {
        await request();
        if (okMsg) toast.success(okMsg);
        await load();
        return true;
      } catch (err) {
        toast.error(apiError(err.response?.data?.detail));
        return false;
      }
    },
    [load]
  );

  const paramById = useMemo(() => Object.fromEntries(params.map((p) => [p.id, p])), [params]);
  const resultsById = useMemo(
    () => Object.fromEntries((batch?.results || []).map((r) => [r.parameter_id, r])),
    [batch]
  );

  return {
    batch,
    params,
    paramById,
    resultsById,
    instruments,
    customers,
    entries,
    setEntries,
    instrumentId,
    setInstrumentId,
    productionDate,
    setProductionDate,
    call,
  };
}

export function buildResultPayload(batch, paramById, resultsById, entries) {
  return (batch.applied_limits || [])
    .map((limit) => {
      const parameter = paramById[limit.parameter_id];
      const entry = entries[limit.parameter_id];
      if (!parameter || !entry || entry.value === "") return null;
      const prev = resultsById[limit.parameter_id];
      const unchanged = prev && String(prev.value_numeric ?? prev.value_text ?? "") === String(entry.value);
      if (unchanged) return null;
      const numeric = parameter.value_type === "numeric";
      return {
        parameter_id: limit.parameter_id,
        value_numeric: numeric ? parseFloat(entry.value) : null,
        value_text: numeric ? null : entry.value,
        reason: entry.reason || "",
      };
    })
    .filter(Boolean);
}

export const downloadBlob = (data, filename) => {
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};
