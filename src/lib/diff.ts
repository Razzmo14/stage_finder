/** Word-level diff between two texts (simple LCS). */

export interface DiffPart {
  value: string;
  added: boolean;
  removed: boolean;
}

function lcsMatrix(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

export function diffWords(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/).filter((w) => w.length > 0);
  const b = after.split(/(\s+)/).filter((w) => w.length > 0);
  const table = lcsMatrix(a, b);
  const parts: DiffPart[] = [];
  const push = (value: string, added: boolean, removed: boolean) => {
    const last = parts[parts.length - 1];
    if (last && last.added === added && last.removed === removed) {
      last.value += value;
    } else {
      parts.push({ value, added, removed });
    }
  };
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(a[i], false, false);
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push(a[i], false, true);
      i++;
    } else {
      push(b[j], true, false);
      j++;
    }
  }
  while (i < a.length) push(a[i++], false, true);
  while (j < b.length) push(b[j++], true, false);
  return parts;
}
