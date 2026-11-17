/** Caelum's open-sky C and two speech lines, drawn on a shared 32px grid. */
export function CaelumBrand() {
  return (
    <>
      <svg
        aria-hidden="true"
        viewBox="0 0 32 32"
        fill="none"
        className="size-8! shrink-0"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M25 8a11 11 0 1 0 0 16" />
        <path d="M12 14h14M12 19h10" />
      </svg>
      <span className="text-[22px] font-medium tracking-[-.055em] group-data-[collapsible=icon]:hidden">
        caelum
      </span>
    </>
  );
}
