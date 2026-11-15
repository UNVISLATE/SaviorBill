from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html, get_redoc_html
from fastapi.responses import HTMLResponse, RedirectResponse

from core.config import APP_NAME, APP_VERSION, AppConfig

router = APIRouter(include_in_schema=False)

_SWAGGER_DARK_CSS = """
:root {
  --sb-bg: #0b0d10;
  --sb-surface: #11141a;
  --sb-surface-hover: #161b22;
  --sb-surface-active: #1c222b;
  --sb-border: rgba(255, 255, 255, 0.08);
  --sb-border-hover: rgba(255, 255, 255, 0.16);
  --sb-text: #f8fafc;
  --sb-text-muted: #94a3b8;
  --sb-primary: #009080;
  --sb-primary-hover: #0c5e53;
  --sb-primary-glow: rgba(0, 144, 128, 0.25);
  
  --sb-get: #0284c7;
  --sb-get-bg: rgba(2, 132, 199, 0.08);
  --sb-get-border: rgba(2, 132, 199, 0.28);
  
  --sb-post: #10b981;
  --sb-post-bg: rgba(16, 185, 129, 0.08);
  --sb-post-border: rgba(16, 185, 129, 0.28);
  
  --sb-put: #f59e0b;
  --sb-put-bg: rgba(245, 158, 11, 0.08);
  --sb-put-border: rgba(245, 158, 11, 0.28);
  
  --sb-delete: #ef4444;
  --sb-delete-bg: rgba(239, 68, 68, 0.08);
  --sb-delete-border: rgba(239, 68, 68, 0.28);
  
  --sb-patch: #a855f7;
  --sb-patch-bg: rgba(168, 85, 247, 0.08);
  --sb-patch-border: rgba(168, 85, 247, 0.28);
}

html, body {
  background-color: var(--sb-bg) !important;
  color: var(--sb-text) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
  margin: 0;
  padding: 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.25);
}

/* Header bar */
.sb-docs-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: rgba(11, 13, 16, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--sb-border);
  height: 54px;
  display: flex;
  align-items: center;
  padding: 0 24px;
}
.sb-docs-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 1460px;
  margin: 0 auto;
}
.sb-docs-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
}
.sb-docs-logo {
  width: 22px;
  height: 22px;
  color: var(--sb-primary);
  flex-shrink: 0;
}
.sb-docs-title {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #ffffff;
}
.sb-docs-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(0, 144, 128, 0.15);
  color: #009080;
  border: 1px solid rgba(0, 144, 128, 0.3);
}
.sb-docs-version {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--sb-text-muted);
}
.sb-docs-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  color: var(--sb-text-muted);
  text-decoration: none;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.sb-nav-link:hover {
  color: var(--sb-text);
  background: var(--sb-surface-hover);
  border-color: var(--sb-border);
}
.sb-nav-link.active {
  color: #ffffff;
  background: rgba(0, 144, 128, 0.15);
  border-color: rgba(0, 144, 128, 0.35);
}
.sb-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  color: var(--sb-text);
  background: var(--sb-surface);
  border: 1px solid var(--sb-border);
  text-decoration: none;
  transition: all 0.15s ease;
}
.sb-nav-btn:hover {
  border-color: rgba(0, 144, 128, 0.5);
  background: var(--sb-surface-hover);
}
.sb-nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
}

/* Swagger UI overrides */
.swagger-ui {
  color: var(--sb-text) !important;
  font-family: inherit !important;
  max-width: 1460px;
  margin: 0 auto;
  padding: 20px 24px 60px 24px;
}
.swagger-ui .topbar {
  display: none !important;
}
.swagger-ui .wrapper {
  padding: 0 !important;
  max-width: 100% !important;
}

/* Info container */
.swagger-ui .info {
  background: var(--sb-surface) !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 12px !important;
  padding: 24px 28px !important;
  margin: 0 0 24px 0 !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
}
.swagger-ui .info .title {
  color: #ffffff !important;
  font-weight: 700 !important;
  font-size: 26px !important;
  letter-spacing: -0.02em !important;
}
.swagger-ui .info .title small {
  background: rgba(0, 144, 128, 0.15) !important;
  color: #009080 !important;
  border: 1px solid rgba(0, 144, 128, 0.3) !important;
  border-radius: 9999px !important;
  font-size: 11px !important;
  padding: 2px 8px !important;
  font-weight: 600 !important;
  top: -4px !important;
  margin-left: 10px !important;
}
.swagger-ui .info p, .swagger-ui .info li {
  color: var(--sb-text-muted) !important;
  font-size: 14px !important;
  line-height: 1.6 !important;
}
.swagger-ui .info a {
  color: #009080 !important;
  text-decoration: underline !important;
  text-underline-offset: 3px !important;
}
.swagger-ui .info code {
  background: #171b23 !important;
  color: #e2e8f0 !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 4px !important;
  padding: 2px 6px !important;
  font-size: 12px !important;
}

/* Scheme & Authorize container */
.swagger-ui .scheme-container {
  background: transparent !important;
  box-shadow: none !important;
  border-bottom: 1px solid var(--sb-border) !important;
  padding: 16px 0 !important;
  margin-bottom: 20px !important;
}
.swagger-ui .schemes > label {
  color: var(--sb-text-muted) !important;
  font-size: 13px !important;
}
.swagger-ui select {
  background: var(--sb-surface) !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 6px !important;
  color: var(--sb-text) !important;
  padding: 6px 10px !important;
}
.swagger-ui .btn.authorize {
  background: #009080 !important;
  color: #ffffff !important;
  border: none !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  padding: 7px 18px !important;
  box-shadow: 0 2px 10px rgba(0, 144, 128, 0.3) !important;
  transition: all 0.15s ease !important;
}
.swagger-ui .btn.authorize:hover {
  background: #0c5e53 !important;
  box-shadow: 0 4px 14px rgba(0, 144, 128, 0.45) !important;
}
.swagger-ui .btn.authorize svg {
  fill: #ffffff !important;
}

/* Filter container */
.swagger-ui .filter-container {
  padding: 12px 0 20px 0 !important;
}
.swagger-ui .filter-container .operation-filter-input {
  background: var(--sb-surface) !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 8px !important;
  color: var(--sb-text) !important;
  padding: 9px 14px !important;
  width: 100% !important;
  max-width: 420px !important;
  outline: none !important;
  transition: all 0.15s ease !important;
}
.swagger-ui .filter-container .operation-filter-input:focus {
  border-color: #009080 !important;
  box-shadow: 0 0 0 2px var(--sb-primary-glow) !important;
}

/* Tags & Opblocks */
.swagger-ui .opblock-tag {
  border-bottom: 1px solid var(--sb-border) !important;
  color: var(--sb-text) !important;
  font-size: 17px !important;
  font-weight: 600 !important;
  padding: 14px 0 !important;
  margin-top: 14px !important;
}
.swagger-ui .opblock-tag small {
  color: var(--sb-text-muted) !important;
  font-size: 13px !important;
  font-weight: 400 !important;
}
.swagger-ui .opblock-tag:hover {
  color: #009080 !important;
}
.swagger-ui .opblock-tag svg {
  fill: var(--sb-text-muted) !important;
}

/* Opblocks (Endpoints) */
.swagger-ui .opblock {
  background: var(--sb-surface) !important;
  border-radius: 10px !important;
  margin: 0 0 10px 0 !important;
  box-shadow: none !important;
  border: 1px solid var(--sb-border) !important;
  transition: border-color 0.15s ease, background-color 0.15s ease !important;
}
.swagger-ui .opblock:hover {
  border-color: var(--sb-border-hover) !important;
}
.swagger-ui .opblock .opblock-summary {
  padding: 10px 14px !important;
}
.swagger-ui .opblock .opblock-summary-method {
  border-radius: 6px !important;
  font-weight: 700 !important;
  font-size: 11.5px !important;
  min-width: 72px !important;
  text-align: center !important;
  padding: 6px 0 !important;
  letter-spacing: 0.04em !important;
}
.swagger-ui .opblock .opblock-summary-path {
  color: #f1f5f9 !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 13.5px !important;
}
.swagger-ui .opblock .opblock-summary-description {
  color: var(--sb-text-muted) !important;
  font-size: 13px !important;
}
.swagger-ui .opblock svg.arrow {
  fill: var(--sb-text-muted) !important;
}

/* Methods styling */
.swagger-ui .opblock.opblock-get {
  border-color: var(--sb-get-border) !important;
  background: var(--sb-get-bg) !important;
}
.swagger-ui .opblock.opblock-get .opblock-summary-method {
  background: var(--sb-get) !important;
  color: #ffffff !important;
}

.swagger-ui .opblock.opblock-post {
  border-color: var(--sb-post-border) !important;
  background: var(--sb-post-bg) !important;
}
.swagger-ui .opblock.opblock-post .opblock-summary-method {
  background: var(--sb-post) !important;
  color: #ffffff !important;
}

.swagger-ui .opblock.opblock-put {
  border-color: var(--sb-put-border) !important;
  background: var(--sb-put-bg) !important;
}
.swagger-ui .opblock.opblock-put .opblock-summary-method {
  background: var(--sb-put) !important;
  color: #ffffff !important;
}

.swagger-ui .opblock.opblock-delete {
  border-color: var(--sb-delete-border) !important;
  background: var(--sb-delete-bg) !important;
}
.swagger-ui .opblock.opblock-delete .opblock-summary-method {
  background: var(--sb-delete) !important;
  color: #ffffff !important;
}

.swagger-ui .opblock.opblock-patch {
  border-color: var(--sb-patch-border) !important;
  background: var(--sb-patch-bg) !important;
}
.swagger-ui .opblock.opblock-patch .opblock-summary-method {
  background: var(--sb-patch) !important;
  color: #ffffff !important;
}

/* Opblock Body (Expanded) */
.swagger-ui .opblock-body {
  background: #0d0f14 !important;
  border-top: 1px solid var(--sb-border) !important;
  border-radius: 0 0 10px 10px !important;
  padding: 20px !important;
}
.swagger-ui .opblock-section-header {
  background: transparent !important;
  box-shadow: none !important;
  border-bottom: 1px solid var(--sb-border) !important;
  padding: 10px 0 !important;
}
.swagger-ui .opblock-section-header h4 {
  color: #f1f5f9 !important;
  font-size: 13px !important;
  font-weight: 600 !important;
}
.swagger-ui .tab {
  color: var(--sb-text-muted) !important;
}
.swagger-ui .tab.active {
  color: #009080 !important;
  border-bottom: 2px solid #009080 !important;
}

/* Tables & Parameters */
.swagger-ui table thead tr th {
  color: var(--sb-text-muted) !important;
  font-size: 11px !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  border-bottom: 1px solid var(--sb-border) !important;
  padding: 10px 12px !important;
}
.swagger-ui table tbody tr td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
  color: var(--sb-text) !important;
  padding: 10px 12px !important;
}
.swagger-ui .parameter__name {
  color: #f8fafc !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 13px !important;
}
.swagger-ui .parameter__name.required:after {
  color: #ef4444 !important;
}
.swagger-ui .parameter__type {
  color: #009080 !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 12px !important;
}
.swagger-ui .parameter__in {
  color: #64748b !important;
  font-style: italic !important;
}
.swagger-ui .parameter__deprecated {
  color: #64748b !important;
  text-decoration: line-through !important;
}

/* Inputs, Textareas, Selects */
.swagger-ui input[type=text],
.swagger-ui input[type=password],
.swagger-ui input[type=search],
.swagger-ui input[type=email],
.swagger-ui textarea {
  background: var(--sb-surface) !important;
  border: 1px solid var(--sb-border) !important;
  color: #f8fafc !important;
  border-radius: 6px !important;
  padding: 7px 10px !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 13px !important;
  transition: all 0.15s ease !important;
}
.swagger-ui input[type=text]:focus,
.swagger-ui input[type=password]:focus,
.swagger-ui textarea:focus {
  border-color: #009080 !important;
  outline: none !important;
  box-shadow: 0 0 0 2px var(--sb-primary-glow) !important;
}

/* Buttons */
.swagger-ui .btn {
  border-radius: 6px !important;
  border: 1px solid var(--sb-border) !important;
  color: #e2e8f0 !important;
  background: var(--sb-surface) !important;
  font-weight: 500 !important;
  font-size: 13px !important;
  transition: all 0.15s ease !important;
}
.swagger-ui .btn:hover {
  background: var(--sb-surface-hover) !important;
  border-color: var(--sb-border-hover) !important;
  color: #ffffff !important;
}
.swagger-ui .btn.execute {
  background: #009080 !important;
  border: none !important;
  color: #ffffff !important;
  font-weight: 600 !important;
  box-shadow: 0 2px 10px rgba(0, 144, 128, 0.3) !important;
}
.swagger-ui .btn.execute:hover {
  background: #0c5e53 !important;
}
.swagger-ui .btn.cancel {
  background: rgba(239, 68, 68, 0.12) !important;
  border-color: rgba(239, 68, 68, 0.3) !important;
  color: #fca5a5 !important;
}
.swagger-ui .btn.cancel:hover {
  background: rgba(239, 68, 68, 0.22) !important;
}

/* Responses & Code Blocks */
.swagger-ui .responses-inner {
  background: transparent !important;
}
.swagger-ui .responses-table {
  background: transparent !important;
}
.swagger-ui .response-col_status {
  color: #f8fafc !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-weight: 600 !important;
}
.swagger-ui .response-col_description {
  color: #cbd5e1 !important;
}
.swagger-ui pre, .swagger-ui .highlight-code {
  background: #07080a !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 8px !important;
  color: #e2e8f0 !important;
  padding: 12px !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
}
.swagger-ui .microlight {
  color: #e2e8f0 !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
}

/* Models */
.swagger-ui section.models {
  background: var(--sb-surface) !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 12px !important;
  margin-top: 30px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
}
.swagger-ui section.models h4 {
  color: #f8fafc !important;
  border-bottom: 1px solid var(--sb-border) !important;
  padding: 14px 20px !important;
  font-size: 15px !important;
  font-weight: 600 !important;
}
.swagger-ui section.models svg {
  fill: var(--sb-text-muted) !important;
}
.swagger-ui .model-box {
  background: transparent !important;
  color: var(--sb-text) !important;
}
.swagger-ui .model-title {
  color: #f8fafc !important;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 13px !important;
}
.swagger-ui .model {
  color: var(--sb-text-muted) !important;
}
.swagger-ui .prop-type {
  color: #009080 !important;
}
.swagger-ui .prop-format {
  color: #64748b !important;
}

/* Dialog / Modal (Authorize) */
.swagger-ui .dialog-ux .backdrop-ux {
  background: rgba(0, 0, 0, 0.75) !important;
  backdrop-filter: blur(4px) !important;
  -webkit-backdrop-filter: blur(4px) !important;
}
.swagger-ui .dialog-ux .modal-ux {
  background: #11141a !important;
  border: 1px solid var(--sb-border) !important;
  border-radius: 12px !important;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.7) !important;
  color: var(--sb-text) !important;
}
.swagger-ui .dialog-ux .modal-ux-header {
  border-bottom: 1px solid var(--sb-border) !important;
  padding: 16px 20px !important;
}
.swagger-ui .dialog-ux .modal-ux-header h3 {
  color: #ffffff !important;
  font-size: 17px !important;
}
.swagger-ui .dialog-ux .modal-ux-header svg {
  fill: var(--sb-text-muted) !important;
}
.swagger-ui .dialog-ux .modal-ux-content {
  padding: 20px !important;
  color: var(--sb-text-muted) !important;
}
.swagger-ui .dialog-ux .modal-ux-content h4 {
  color: #f8fafc !important;
}
"""

_REDOC_DARK_CSS = """
html, body {
  background-color: #090a0d !important;
  color: #f8fafc !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
  margin: 0;
  padding: 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
}
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
}
.sb-docs-header {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: rgba(11, 13, 16, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  height: 54px;
  display: flex;
  align-items: center;
  padding: 0 24px;
}
.sb-docs-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 1460px;
  margin: 0 auto;
}
.sb-docs-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
}
.sb-docs-logo {
  width: 22px;
  height: 22px;
  color: #009080;
  flex-shrink: 0;
}
.sb-docs-title {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: #ffffff;
}
.sb-docs-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(0, 144, 128, 0.15);
  color: #009080;
  border: 1px solid rgba(0, 144, 128, 0.3);
}
.sb-docs-version {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #94a3b8;
}
.sb-docs-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sb-nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  text-decoration: none;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}
.sb-nav-link:hover {
  color: #f8fafc;
  background: #161b22;
  border-color: rgba(255, 255, 255, 0.08);
}
.sb-nav-link.active {
  color: #ffffff;
  background: rgba(0, 144, 128, 0.15);
  border-color: rgba(0, 144, 128, 0.35);
}
.sb-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  color: #f8fafc;
  background: #11141a;
  border: 1px solid rgba(255, 255, 255, 0.08);
  text-decoration: none;
  transition: all 0.15s ease;
}
.sb-nav-btn:hover {
  border-color: rgba(0, 144, 128, 0.5);
  background: #161b22;
}
.sb-nav-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
}
"""


def _render_header(active_tab: str = "swagger") -> str:
    swagger_active = " active" if active_tab == "swagger" else ""
    redoc_active = " active" if active_tab == "redoc" else ""
    return f"""
    <header class="sb-docs-header">
      <div class="sb-docs-container">
        <a href="/about" class="sb-docs-brand">
          <svg class="sb-docs-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span class="sb-docs-title">SaviorBill</span>
          <span class="sb-docs-badge">API Docs</span>
          <span class="sb-docs-version">v{APP_VERSION}</span>
        </a>
        <nav class="sb-docs-nav">
          <a href="/api/docs" class="sb-nav-link{swagger_active}">Swagger UI</a>
          <a href="/api/redoc" class="sb-nav-link{redoc_active}">ReDoc</a>
          <a href="/api/openapi.json" target="_blank" rel="noreferrer" class="sb-nav-link">OpenAPI JSON</a>
          <a href="/about" class="sb-nav-btn">
            <span class="sb-nav-dot"></span>
            <span>Панель управления</span>
          </a>
        </nav>
      </div>
    </header>
    """


@router.get("/docs", response_class=HTMLResponse)
async def swagger_ui(request: Request) -> HTMLResponse:
    settings: AppConfig = getattr(request.app.state, "settings", None)
    if settings and not settings.DOCS_ENABLED:
        raise HTTPException(status_code=404, detail="API documentation is disabled")

    base_response = get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title=f"{APP_NAME} API Documentation - Swagger UI",
        oauth2_redirect_url="/api/docs/oauth2-redirect",
        swagger_ui_parameters={
            "docExpansion": "list",
            "filter": True,
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "defaultModelsExpandDepth": 1,
            "tryItOutEnabled": True,
            "syntaxHighlight.theme": "monokai",
        },
    )

    body = base_response.body.decode("utf-8")
    header_html = _render_header("swagger")

    # Внедряем кастомные стили в <head> и верхнюю панель в <body>
    styled_body = body.replace(
        "</head>",
        f"<style>{_SWAGGER_DARK_CSS}</style></head>",
    )
    if "<body>" in styled_body:
        styled_body = styled_body.replace("<body>", f"<body>{header_html}")

    return HTMLResponse(content=styled_body)


@router.get("/v1/docs")
async def v1_docs_redirect():
    """Алиас для доступа к документации по пути /api/v1/docs."""
    return RedirectResponse(url="/api/docs", status_code=307)


@router.get("/redoc", response_class=HTMLResponse)
async def redoc(request: Request) -> HTMLResponse:
    settings: AppConfig = getattr(request.app.state, "settings", None)
    if settings and not settings.DOCS_ENABLED:
        raise HTTPException(status_code=404, detail="API documentation is disabled")

    base_response = get_redoc_html(
        openapi_url="/api/openapi.json",
        title=f"{APP_NAME} API Specification - ReDoc",
    )

    body = base_response.body.decode("utf-8")
    header_html = _render_header("redoc")

    redoc_theme_tag = """
    <redoc spec-url="/api/openapi.json" theme='{
      "colors": {
        "primary": { "main": "#009080" },
        "text": { "primary": "#f1f5f9", "secondary": "#94a3b8" },
        "http": {
          "get": "#0284c7",
          "post": "#10b981",
          "put": "#f59e0b",
          "delete": "#ef4444"
        }
      },
      "typography": {
        "fontSize": "14px",
        "fontFamily": "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
        "headings": { "fontFamily": "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif" },
        "code": { "fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace" }
      },
      "sidebar": {
        "backgroundColor": "#101318",
        "textColor": "#94a3b8",
        "activeTextColor": "#ffffff"
      },
      "rightPanel": {
        "backgroundColor": "#090a0d",
        "textColor": "#f1f5f9"
      },
      "schema": {
        "nestedBackground": "#141720"
      }
    }'></redoc>
    """

    styled_body = body.replace(
        "</head>",
        f"<style>{_REDOC_DARK_CSS}</style></head>",
    )
    # Заменяем дефолтный тег <redoc> на кастомизированный с темой
    if '<redoc spec-url="/api/openapi.json"></redoc>' in styled_body:
        styled_body = styled_body.replace(
            '<redoc spec-url="/api/openapi.json"></redoc>',
            redoc_theme_tag,
        )
    if "<body>" in styled_body:
        styled_body = styled_body.replace("<body>", f"<body>{header_html}")

    return HTMLResponse(content=styled_body)


@router.get("/v1/redoc")
async def v1_redoc_redirect():
    """Алиас для доступа к спецификации по пути /api/v1/redoc."""
    return RedirectResponse(url="/api/redoc", status_code=307)


@router.get("/docs/oauth2-redirect", response_class=HTMLResponse)
async def swagger_oauth2_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()
