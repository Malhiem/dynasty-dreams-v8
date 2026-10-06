export default function FranchiseRecords({seasons, visibleYears}: {seasons: any[]; visibleYears: Set<number>}) {
  const rows = seasons.filter(s => visibleYears.has(Number(s.year)));
  return <div className="display-case" data-testid="franchise-records">
    <div className="case-label">Franchise Season Records</div>
    {rows.length === 0 ? <p className="text-center text-xs py-3">No season records match this selection.</p> : <div className="overflow-x-auto"><table className="w-full text-xs text-amber-100/80"><thead><tr>{["Season","Rank","W","L","T","Points"].map(label => <th key={label} scope="col" className="p-2">{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.year} data-testid={`franchise-record-${row.year}`}><th scope="row" className="p-2">{row.year}</th><td className="p-2 text-center">{row.rank ?? "Unavailable (legacy standings not saved)"}</td><td className="p-2 text-center">{row.wins ?? 0}</td><td className="p-2 text-center">{row.losses ?? 0}</td><td className="p-2 text-center">{row.ties ?? 0}</td><td className="p-2 text-center">{Number(row.points_for || 0).toLocaleString()}</td></tr>)}</tbody></table></div>}
  </div>;
}
