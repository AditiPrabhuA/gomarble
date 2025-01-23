#!/usr/bin/env bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/.cache/playwright

apt-get update && apt-get install -y \
  libgstreamer-gl1.0-0 \
  libgstreamer-plugins-bad1.0-0 \
  libenchant-2.so.2 \
  libsecret-1.so.0  \
  libmanette-0.2.so.0  \
  libgles2-mesa \
  libgstreamer-plugins-base1.0-0 \
  libgstreamer1.0-0 \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-libav \
  libatk-bridge2.0-0 \
  libatk1.0-0 \
  libcups2 \
  libdrm2 \
  libgbm1 \
  libnspr4 \
  libnss3 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  xdg-utils \
  libasound2 \
  libxshmfence1 \
  libx11-xcb1 \
  libxcb-dri3-0 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libgbm1 \
  libgtk-3-0 \
  libxshmfence1 \
  libegl1 \
  libGLESv2.so.2 \
  libgstcodecparsers-1.0.so.0 \
  libgstgl-1.0.so.0 
playwright install
uvicorn backend.app:app --host 0.0.0.0 --port $PORT