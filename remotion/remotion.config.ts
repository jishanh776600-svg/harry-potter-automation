/**
 * STORY FORGE Remotion Configuration (Step 4)
 * ============================================================================
 * Standardized vertical YouTube Short composition parameters:
 * - 1080x1920 (9:16)
 * - 30 FPS
 * - H.264 / yuv420p
 */

import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setCrf(20);
