/** Caelum's published logo mark, shared with website/mark.svg and the app icons. */
export function CaelumBrand() {
  return (
    <>
      <svg
        aria-hidden="true"
        viewBox="0 0 40 40"
        fill="none"
        className="size-8! shrink-0"
        stroke="currentColor"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M8 25V15m6 16V9m6 25V6m6 25V9m6 16V15" />
      </svg>
      <span className="text-[22px] font-medium tracking-[-.055em] group-data-[collapsible=icon]:hidden">
        caelum
      </span>
    </>
  );
}
