import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolActivityCard } from "./ToolActivityCard";
import type { ScoutMessage } from "../api/types";

const toolMsg: ScoutMessage = {
  id: "m1",
  thread_id: "t1",
  role: "tool",
  content: "[web_search]",
  tool_name: "web_search",
  tool_args: { query: "plumber" },
  tool_result: { result: [{ title: "A" }], error: null },
  created_at: null,
};

describe("ToolActivityCard", () => {
  it("renders tool name and args", () => {
    render(<ToolActivityCard message={toolMsg} />);
    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(screen.getByText(/plumber/)).toBeInTheDocument();
  });

  it("renders the error when the tool failed", () => {
    render(<ToolActivityCard message={{ ...toolMsg, tool_result: { result: null, error: "boom" } }} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
