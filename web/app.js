const $ = (s) => document.querySelector(s);
let current = null;
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function api(url, options = {}) {
  const r = await fetch(url, options),
    data = await r.json();
  if (!r.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
async function busy(fn) {
  $("#run").disabled = true;
  $("#upload").disabled = true;
  $("#message").textContent = "Running local neural OCR…";
  try {
    render(await fn());
    $("#message").textContent =
      "Extraction complete. Inspect the evidence and review the values.";
    await history();
  } catch (e) {
    $("#message").textContent = e.message;
  } finally {
    $("#run").disabled = false;
    $("#upload").disabled = false;
  }
}
$("#run").onclick = () =>
  busy(() => api("/api/sample/" + $("#sample").value, { method: "POST" }));
$("#upload").onchange = (e) => {
  if (!e.target.files[0]) return;
  const f = new FormData();
  f.append("file", e.target.files[0]);
  busy(() => api("/api/upload", { method: "POST", body: f }));
};
function highlight(id) {
  document
    .querySelectorAll("polygon")
    .forEach((p) => p.classList.toggle("active", p.dataset.id === String(id)));
}
function render(d) {
  current = d;
  $("#status").textContent =
    d.status.replaceAll("_", " ") + " · r" + d.revision;
  $("#linecount").textContent = d.lines.length + " OCR regions";
  $("#canvas").innerHTML =
    `<svg viewBox="0 0 ${d.width} ${d.height}" role="img" aria-label="Invoice with OCR evidence regions"><image href="/api/documents/${d.id}/image" width="${d.width}" height="${d.height}"/>${d.lines.map((l) => `<polygon data-id="${l.id}" points="${l.box.map((p) => p.join(",")).join(" ")}"><title>${esc(l.text)}</title></polygon>`).join("")}</svg>`;
  $("#review").innerHTML =
    `<div class="checks ${d.issues.length ? "" : "good"}">${d.issues.length ? d.issues.map(esc).join("<br>") : d.status === "approved" ? "✓ Checks pass. This revision has been approved by the local reviewer." : "✓ Required fields and arithmetic checks pass. Human review still required."}</div>${Object.entries(
      d.values,
    )
      .map(([k, v]) => {
        const f = d.extracted[k];
        return `<div class="field"><label for="field-${k}">${k.replaceAll("_", " ")}</label><input id="field-${k}" data-key="${k}" value="${esc(v)}" maxlength="200"><button type="button" class="source" data-source="${f.source}" title="Highlight original OCR evidence">${f.source === null ? "No source" : `OCR ${(f.ocr_score * 100).toFixed(0)} · ↗`}</button></div>`;
      })
      .join(
        "",
      )}<label for="note">REVIEW NOTE (REQUIRED)</label><textarea id="note" placeholder="Describe what you checked or corrected…" rows="2" maxlength="1000"></textarea><div class="actions"><button id="approve">Approve document</button><button id="save" class="secondary">Save changes</button><a href="/api/documents/${d.id}/export">Export JSON ↗</a></div><p class="hint">Approving records a local reviewer action. OCR scores are not confidence guarantees.</p>`;
  document
    .querySelectorAll("[data-source]")
    .forEach((b) => (b.onclick = () => highlight(b.dataset.source)));
  document
    .querySelectorAll("[data-key]")
    .forEach(
      (i) => (i.onfocus = () => highlight(d.extracted[i.dataset.key].source)),
    );
  $("#approve").onclick = () => review(true);
  $("#save").onclick = () => review(false);
  $("#audit").innerHTML = d.audit
    .slice()
    .reverse()
    .map(
      (a) =>
        `<div class="event"><b>${esc(a.action)}</b> · ${esc(new Date(a.at).toLocaleString())}<div>${esc(a.note || "Neural OCR + rule extraction")}</div>${a.changes && Object.keys(a.changes).length ? `<pre>${esc(JSON.stringify(a.changes, null, 2))}</pre>` : ""}</div>`,
    )
    .join("");
}
async function review(approve) {
  const values = Object.fromEntries(
    [...document.querySelectorAll("[data-key]")].map((i) => [
      i.dataset.key,
      i.value,
    ]),
  );
  const note = $("#note").value.trim();
  if (note.length < 3) {
    $("#message").textContent =
      "Add a review note with at least three characters.";
    return;
  }
  $("#approve").disabled = $("#save").disabled = true;
  try {
    render(
      await api(`/api/documents/${current.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          values,
          note,
          approve,
          revision: current.revision,
        }),
      }),
    );
    $("#message").textContent = approve
      ? "Approved. The audit trail and export are updated."
      : "Review saved.";
    await history();
  } catch (e) {
    $("#message").textContent = e.message;
    $("#approve").disabled = $("#save").disabled = false;
  }
}
async function history() {
  const docs = await api("/api/documents");
  $("#history").innerHTML =
    '<option value="">Select saved document…</option>' +
    docs
      .map(
        (d) =>
          `<option value="${d.id}">${esc(d.invoice || "Untitled")} · ${esc(d.status)} · ${d.id.slice(0, 6)}</option>`,
      )
      .join("");
}
$("#history").onchange = async (e) => {
  if (e.target.value) {
    try {
      render(await api("/api/documents/" + e.target.value));
    } catch (err) {
      $("#message").textContent = err.message;
    }
  }
};
history().catch((e) => ($("#message").textContent = e.message));
