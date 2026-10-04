import Link from "next/link";

export default function NotFound() {
  return (
    <div className="empty">
      <p className="empty-title">Halaman tidak ditemukan</p>
      <Link href="/">Kembali ke Dashboard</Link>
    </div>
  );
}
