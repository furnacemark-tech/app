// Test-only stub for react-router-dom.
// react-router-dom v7 ships an ESM/"exports" package whose `main` points to a
// non-existent dist/main.js, which Jest's CJS resolver cannot load. The router
// is not the subject under test here; QAQueues only needs <Link> and
// useNavigate, and tests wrap with a passthrough <MemoryRouter>.
import React from "react";

export const MemoryRouter = ({ children }) => <>{children}</>;

export const Link = ({ to, children, ...rest }) => (
  <a href={typeof to === "string" ? to : "#"} {...rest}>
    {children}
  </a>
);

export const useNavigate = () => () => {};
