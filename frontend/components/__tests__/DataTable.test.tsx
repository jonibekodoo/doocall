import { NextIntlClientProvider } from "next-intl";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ru from "@/messages/ru.json";
import { DataTable, type Column } from "@/components/ui/DataTable";

interface Row {
  id: number;
  name: string;
}

const columns: Column<Row>[] = [
  { key: "name", header: "Имя", cell: (row) => row.name },
];

function renderTable(
  props: Partial<Parameters<typeof DataTable<Row>>[0]> = {},
) {
  return render(
    <NextIntlClientProvider locale="ru" messages={ru}>
      <DataTable<Row> columns={columns} rows={[]} {...props} />
    </NextIntlClientProvider>,
  );
}

describe("DataTable", () => {
  it("renders the localized empty state when there are no rows", () => {
    renderTable();
    expect(screen.getByTestId("table-empty")).toHaveTextContent(
      "Данных пока нет",
    );
  });

  it("renders skeleton rows while loading (and no empty state)", () => {
    renderTable({ loading: true, skeletonRows: 5 });
    expect(screen.getAllByTestId("skeleton-row")).toHaveLength(5);
    expect(screen.queryByTestId("table-empty")).not.toBeInTheDocument();
  });

  it("renders data rows when provided", () => {
    renderTable({ rows: [{ id: 1, name: "Aziz" }] });
    expect(screen.getByText("Aziz")).toBeInTheDocument();
    expect(screen.queryByTestId("table-empty")).not.toBeInTheDocument();
  });

  it("supports a custom empty slot", () => {
    renderTable({ empty: <p>Совсем пусто</p> });
    expect(screen.getByText("Совсем пусто")).toBeInTheDocument();
  });
});
