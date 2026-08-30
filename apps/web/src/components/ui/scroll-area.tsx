import * as React from "react";
import { cn } from "@/lib/utils";

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  showHorizontalScrollbar?: boolean;
  showVerticalScrollbar?: boolean;
}

const ScrollArea = React.forwardRef<
  HTMLDivElement,
  ScrollAreaProps
>(({ className, children, showHorizontalScrollbar, showVerticalScrollbar, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("overflow-auto", className, {
      "scrollbar-thin": !showHorizontalScrollbar && !showVerticalScrollbar,
      "scrollbar-none": !showVerticalScrollbar,
    })}
    {...props}
  >
    {children}
  </div>
));
ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
