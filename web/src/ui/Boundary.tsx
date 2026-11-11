import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { Component, type ReactNode, Suspense } from "react";
import { useMessages } from "../i18n";

class Catch extends Component<
  { fallback: (retry: () => void) => ReactNode; onReset: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return this.props.fallback(() => {
      this.props.onReset();
      this.setState({ failed: false });
    });
  }
}

/**
 * Shows a loading line while its content waits for data, and a retry action
 * when the data fails. A failure stays inside this boundary: the rest of the
 * page keeps working.
 */
export function Boundary(props: { children: ReactNode }) {
  const t = useMessages();
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <Catch
          onReset={reset}
          fallback={(retry) => (
            <div role="alert" className="grid justify-items-start gap-3">
              <p>{t.common.loadFailed}</p>
              <button type="button" className="button-quiet" onClick={retry}>
                {t.common.retry}
              </button>
            </div>
          )}
        >
          <Suspense fallback={<p className="text-muted">{t.common.loading}</p>}>
            {props.children}
          </Suspense>
        </Catch>
      )}
    </QueryErrorResetBoundary>
  );
}
