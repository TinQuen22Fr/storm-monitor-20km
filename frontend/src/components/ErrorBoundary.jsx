import React from "react";

/**
 * Catches rendering errors in a subtree and shows an inline error card
 * instead of crashing the whole page (no more white screen in production).
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        <div
          className="border border-rose-200 bg-rose-50 p-5"
          data-testid="error-boundary"
        >
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-rose-700">
            Erreur de rendu
          </div>
          <div className="mt-2 text-sm text-rose-900">
            {this.props.label || "Une erreur est survenue dans ce composant."}
          </div>
          <pre className="mt-2 text-[10px] font-mono text-rose-700 whitespace-pre-wrap break-words max-h-32 overflow-auto">
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button
            onClick={this.reset}
            className="mt-3 px-3 py-1 text-[10px] font-mono uppercase tracking-[0.2em] border border-rose-300 text-rose-800 hover:bg-rose-100"
            data-testid="error-boundary-retry"
          >
            Réessayer
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
