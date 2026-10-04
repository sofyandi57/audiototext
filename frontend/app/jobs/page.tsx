"use client";

import Link from "next/link";
import { api, fmtDate, Job } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { Empty, ErrorBox, JobPanel, Loading } from "@/components/ui";

export default function JobsPage() {
  const jobs = useResource(
    () => api<Job[]>("/api/jobs?limit=100"),
    [],
    (d) => !!d?.some((j) => j.status === "queued" || j.status === "running"),
    2500,
  );
  return (
    <>
      <h1>Jobs</h1>
      <p className="muted small">Pekerjaan diproses satu per satu di CPU. Pekerjaan yang terputus dilanjutkan otomatis.</p>
      <ErrorBox error={jobs.error} onRetry={jobs.refresh} />
      {jobs.loading && !jobs.data ? (
        <Loading />
      ) : !jobs.data?.length ? (
        <Empty title="Belum ada pekerjaan" />
      ) : (
        <ul className="list" data-testid="jobs">
          {jobs.data.map((j) => (
            <li key={j.id}>
              <JobPanel job={j} onChange={jobs.refresh} compact />
              <p className="muted small">
                {j.target_name ? (
                  <Link href={j.target_type === "document" ? `/audiobooks/view/?id=${j.target_id}` : `/meetings/view/?id=${j.target_id}`}>
                    {j.target_name}
                  </Link>
                ) : (
                  "(sudah dihapus)"
                )}{" "}
                · {fmtDate(j.created_at)} · <code>{j.id}</code>
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
