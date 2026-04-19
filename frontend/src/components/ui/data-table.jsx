import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

export function DataTable({ columns, data, onRowClick, testId }) {
  return (
    <div className="surface overflow-hidden" data-testid={testId}>
      <Table>
        <TableHeader>
          <TableRow className="border-b border-white/10 hover:bg-transparent">
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className="text-[#A1A1AA] text-xs uppercase tracking-wider font-semibold"
              >
                {col.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row, i) => (
            <TableRow
              key={row.id || i}
              onClick={() => onRowClick?.(row)}
              className={`border-b border-white/10 ${onRowClick ? 'cursor-pointer hover:bg-[#1A1A1A]' : ''}`}
            >
              {columns.map((col) => (
                <TableCell key={col.key} className="text-white">
                  {col.render ? col.render(row[col.key], row) : row[col.key]}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
