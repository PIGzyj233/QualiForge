export function pickExistingId<T extends { id: string }>(items: T[], preferred?: string, current?: string) {
  if (preferred && items.some((item) => item.id === preferred)) return preferred;
  if (current && items.some((item) => item.id === current)) return current;
  return items[0]?.id ?? "";
}
