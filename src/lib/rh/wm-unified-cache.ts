/** Projection revision changes invalidate expensive coverage aggregates. */
export function revisionCache<T>() {
  let entry: {key: string; value: T} | undefined;
  return (key: string, read: () => T): T => {
    if (!entry || entry.key !== key) entry = {key, value: read()};
    return entry.value;
  };
}
