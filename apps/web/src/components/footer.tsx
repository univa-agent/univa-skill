"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { RiDiscordFill, RiTwitterXLine } from "react-icons/ri";
import { FaGithub } from "react-icons/fa6";
import { getStars } from "@/lib/fetch-github-stars";
import Image from "next/image";

export function Footer() {
  const [star, setStar] = useState<string>();

  useEffect(() => {
    const fetchStars = async () => {
      try {
        const data = await getStars();
        setStar(data);
      } catch (err) {
        console.error("Failed to fetch GitHub stars", err);
      }
    };

    fetchStars();
  }, []);

  return (
    <motion.footer
      className="bg-background border-t"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.8, duration: 0.8 }}
    >
      <div className="max-w-5xl mx-auto px-8 py-10">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-8">
          {/* Brand Section */}
          <div className="md:col-span-1 max-w-sm">
            <div className="flex justify-start items-center gap-2 mb-4">
              <Image src="/favicon.png" alt="UniVA" width={24} height={24} />
              <span className="font-bold text-lg">UniVA</span>
            </div>
            <p className="text-sm md:text-left text-muted-foreground mb-5">
              An all-in-one video creation platform that meets all your video production needs in one stop.
            </p>
            <div className="flex justify-start gap-3">
              <Link
                href="https://github.com/univa-agent"
                className="text-muted-foreground hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                <FaGithub className="h-5 w-5" />
              </Link>
              <Link
                href="https://discord.gg/85GkGW897V"
                className="text-muted-foreground hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                <RiDiscordFill className="h-5 w-5" />
              </Link>
            </div>
          </div>

          <div className="flex gap-12 justify-start items-start py-2">
            <div>
              <h3 className="font-semibold text-foreground mb-4">Resources</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <Link
                    href="https://github.com/univa-agent"
                    className="text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Code
                  </Link>
                </li>
                <li>
                  <Link
                    href="https://huggingface.co/datasets/chr1ce/UniVA-Bench"
                    className="text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Benchmark
                  </Link>
                </li>
              </ul>
            </div>

            {/* Company Links */}
            <div>
              <h3 className="font-semibold text-foreground mb-4">Communication</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <Link
                    href="https://discord.gg/85GkGW897V"
                    className="text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Community
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="pt-2 flex flex-col md:flex-row justify-between items-start gap-4">
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>© 2025 UniVA, All Rights Reserved</span>
          </div>
        </div>
      </div>
    </motion.footer>
  );
}
