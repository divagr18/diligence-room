/* DocumentViewer — open a data-room document at the exact located page (PDF)
   or located sheet+row (XLSX) for a finding's evidence span.

   Backed by GET /api/documents/{id} (serve) and GET /api/documents/{id}/locate
   (locator). The locator reuses the ingestion parser's extraction, so a span
   verified at write time is guaranteed to resolve to a page or a row. */

import { useEffect, useRef } from "react";
import { ExternalLink, X } from "lucide-react";
import { api, documentUrl, useAsync, type DocumentLocator, type XlsxLocator } from "../api";
import { LoadingState, Tag } from "./ui";

interface EvidenceRef {
  document_id: string;
  verbatim_span: string;
  chunk_ref: string | null;
}

function locatorLabel(loc: DocumentLocator): string {
  if (loc.kind === "pdf") {
    return loc.page
      ? `PDF · page ${loc.page} of ${loc.page_count}`
      : `PDF · ${loc.page_count} pages`;
  }
  if ("rows" in loc) {
    const sheet = loc.sheet ?? "sheet";
    const row = loc.row_index !== null ? ` · row ${loc.row_index + 1}` : "";
    return `XLSX · ${sheet}${row}`;
  }
  return loc.kind.toUpperCase();
}

function SourceFallback({ note, href, error }: { note: string; href: string; error?: string }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-6">
      <div className="max-w-md text-center">
        <p className="text-[13px] text-ink2">{note}</p>
        {error ? <p className="mt-2 font-mono text-[12px] text-ink4">{error}</p> : null}
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent transition-colors duration-150 hover:text-ink1"
        >
          <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden />
          Open in browser
        </a>
      </div>
    </div>
  );
}

function XlsxSheet({ locator }: { locator: XlsxLocator }) {
  const { headers, rows, row_index } = locator;
  const body = rows.slice(1); // rows[0] duplicates headers
  const highlightIndex = row_index !== null ? row_index - 1 : -1;
  const highlightedRef = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    highlightedRef.current?.scrollIntoView({ block: "center", inline: "nearest" });
  }, []);

  if (!headers.length) {
    return (
      <div className="px-5 py-8 text-center text-[13px] text-ink3">
        No readable rows in this sheet.
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            {headers.map((h, i) => (
              <th
                key={i}
                scope="col"
                className="whitespace-nowrap px-4 py-2.5 text-[11px] font-medium uppercase tracking-[0.04em] text-ink4"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, i) => {
            const located = highlightIndex >= 0 && i === highlightIndex;
            return (
              <tr
                key={i}
                ref={located ? highlightedRef : undefined}
                className={`border-b border-line last:border-b-0 ${located ? "bg-card2" : ""}`}
              >
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={`whitespace-nowrap px-4 py-2.5 text-[13px] ${
                      located ? "text-ink1" : "text-ink2"
                    } ${located && j === 0 ? "border-l-2 border-l-accent" : ""} ${
                      /\d/.test(cell) ? "tabular font-mono text-[12px]" : ""
                    }`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function DocumentViewer({
  evidence,
  onClose,
}: {
  evidence: EvidenceRef;
  onClose: () => void;
}) {
  const { document_id, verbatim_span, chunk_ref } = evidence;
  const { data: locator, error, loading } = useAsync(
    () => api.locate(document_id, verbatim_span),
    [document_id, verbatim_span],
  );
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const fileHref = documentUrl(document_id);
  const pdfHref =
    locator && locator.kind === "pdf" && locator.page ? `${fileHref}#page=${locator.page}` : fileHref;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Source document ${document_id}`}
        className="flex h-[86vh] w-[min(1080px,94vw)] flex-col overflow-hidden rounded-lg border border-line2 bg-card outline-none"
      >
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="truncate font-mono text-[13px] font-medium text-ink1">{document_id}</div>
            <div className="mt-0.5 font-mono text-[11px] text-ink4">
              {loading
                ? "locating evidence…"
                : error
                  ? "locator unavailable"
                  : locator
                    ? locatorLabel(locator)
                    : ""}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <a
              href={pdfHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-line bg-card px-2.5 py-1.5 text-[12px] font-medium text-ink2 transition-colors duration-150 hover:bg-card2 hover:text-ink1"
            >
              <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden />
              Open in browser
            </a>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close viewer"
              className="inline-flex size-8 items-center justify-center rounded-md border border-line bg-card text-ink3 transition-colors duration-150 hover:bg-card2 hover:text-ink1"
            >
              <X className="size-4" strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        </div>

        <div className="border-b border-line px-5 py-3">
          <blockquote className="border-l-2 border-line3 pl-4 text-[13px] italic leading-relaxed text-ink2">
            “{verbatim_span}”
          </blockquote>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {chunk_ref ? <Tag>{chunk_ref}</Tag> : null}
            <span className="font-mono text-[11px] text-ink4">evidence span · located in source</span>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          {loading ? (
            <LoadingState label={`locating ${document_id}`} />
          ) : error ? (
            <SourceFallback
              note="The Deal Room API could not locate this source."
              error={error}
              href={fileHref}
            />
          ) : locator && locator.kind === "pdf" ? (
            <div className="min-h-0 flex-1 p-2">
              <object data={pdfHref} type="application/pdf" className="h-full w-full rounded-md bg-card2">
                <div className="flex h-full items-center justify-center">
                  <p className="px-6 text-center text-[13px] text-ink2">
                    This browser cannot preview the PDF inline.{" "}
                    <a href={pdfHref} target="_blank" rel="noreferrer" className="text-accent hover:text-ink1">
                      Open it in a new tab
                    </a>
                    .
                  </p>
                </div>
              </object>
            </div>
          ) : locator && "rows" in locator ? (
            <XlsxSheet locator={locator} />
          ) : (
            <SourceFallback note="Source cannot be previewed inline." href={fileHref} />
          )}
        </div>
      </div>
    </div>
  );
}
