"use client";

import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { ArrowRightIcon } from "lucide-react";
import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";

export function Onboarding() {
  const [step, setStep] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const hasSeenOnboarding = localStorage.getItem("hasSeenOnboarding");
    if (!hasSeenOnboarding) {
      setIsOpen(true);
    }
  }, []);

  const handleNext = () => {
    setStep(step + 1);
  };

  const handleClose = () => {
    setIsOpen(false);
    localStorage.setItem("hasSeenOnboarding", "true");
  };

  const getStepTitle = () => {
    switch (step) {
      case 0:
        return "Welcome to UniVA Beta! 🎉";
      case 1:
        return "⚠️ This is a super early beta!";
      case 2:
        return "🦋 Have fun testing!";
      default:
        return "UniVA Onboarding";
    }
  };

  const renderStepContent = () => {
    switch (step) {
      case 0:
        return (
          <div className="space-y-5">
            <div className="space-y-3">
              <Title title="Welcome to UniVA Beta! 🎉" />
              <Description description="You're among the first to try UniVA - the fully open source Universal Video Agent." />
            </div>
            <NextButton onClick={handleNext}>Next</NextButton>
          </div>
        );
      case 1:
        return (
          <div className="space-y-5">
            <div className="space-y-3">
              <Title title={getStepTitle()} />
              <Description description="UniVA still a ton of things to do to update this agent amazing." />
              <Description description="If you're curious, check out our Homepage [here](https://univa.online)" />
            </div>
            <NextButton onClick={handleNext}>Next</NextButton>
          </div>
        );
      case 2:
        return (
          <div className="space-y-5">
            <div className="space-y-3">
              <Title title={getStepTitle()} />
              <Description description="Join our [Discord](https://discord.gg/85GkGW897V), chat with cool people and share feedback to help make UniVA the best editor ever." />
            </div>
            <NextButton onClick={handleClose}>Finish</NextButton>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[425px] outline-hidden!">
        <DialogTitle>
          <span className="sr-only">{getStepTitle()}</span>
        </DialogTitle>
        {renderStepContent()}
      </DialogContent>
    </Dialog>
  );
}

function Title({ title }: { title: string }) {
  return <h2 className="text-lg md:text-xl font-bold">{title}</h2>;
}

function Subtitle({ subtitle }: { subtitle: string }) {
  return <h3 className="text-lg font-medium">{subtitle}</h3>;
}

function Description({ description }: { description: string }) {
  return (
    <div className="text-muted-foreground">
      <ReactMarkdown
        components={{
          p: ({ children }) => <p className="mb-0">{children}</p>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-foreground hover:text-foreground/80 underline"
            >
              {children}
            </a>
          ),
        }}
      >
        {description}
      </ReactMarkdown>
    </div>
  );
}

function NextButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <Button onClick={onClick} variant="default" className="w-full">
      {children}
      <ArrowRightIcon className="w-4 h-4" />
    </Button>
  );
}
