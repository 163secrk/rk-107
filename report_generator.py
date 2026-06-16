from datetime import datetime
from pathlib import Path
from typing import Dict, List
from collections import Counter, defaultdict

from task_scheduler import ProfileResult, FailedFile, SkippedFile


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _status_color_class(result: ProfileResult) -> str:
    if result.failed_count > 0:
        return "status-failed"
    if result.skipped_count > 0:
        return "status-skipped"
    if result.total_files == 0:
        return "status-idle"
    return "status-success"


def _status_text(result: ProfileResult) -> str:
    if result.total_files == 0:
        return "无差异"
    if result.failed_count > 0:
        return f"失败 {result.failed_count} 项"
    if result.skipped_count > 0:
        return f"跳过 {result.skipped_count} 项"
    return "全部成功"


def generate_report(results: List[ProfileResult], output_path: str = None) -> str:
    total_profiles = len(results)
    total_success = sum(r.success_count for r in results)
    total_failed = sum(r.failed_count for r in results)
    total_skipped = sum(r.skipped_count for r in results)
    total_files = sum(r.total_files for r in results)

    error_counter: Counter = Counter()
    error_details: Dict[str, List[FailedFile]] = defaultdict(list)
    all_skipped: List[SkippedFile] = []
    profile_with_issues = 0

    for r in results:
        if r.failed_count > 0 or r.skipped_count > 0:
            profile_with_issues += 1
        for ff in r.failed_files:
            error_counter[ff.error_category] += 1
            error_details[ff.error_category].append(ff)
        all_skipped.extend(r.skipped_files)

    successful_profiles = sum(1 for r in results if r.failed_count == 0 and r.total_files > 0)
    no_diff_profiles = sum(1 for r in results if r.total_files == 0)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report_id = f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>对账审计报告 - {_escape_html(report_id)}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #f0f2f5;
    color: #1f2937;
    line-height: 1.6;
    padding: 32px 16px;
}}
.container {{
    max-width: 1200px;
    margin: 0 auto;
}}
.report-header {{
    background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
    color: white;
    padding: 36px 40px;
    border-radius: 16px;
    box-shadow: 0 10px 40px rgba(37, 99, 235, 0.2);
    margin-bottom: 28px;
}}
.report-header h1 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 8px;
}}
.report-header .subtitle {{
    font-size: 14px;
    opacity: 0.9;
    margin-bottom: 20px;
}}
.report-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    font-size: 14px;
    opacity: 0.95;
}}
.report-meta .meta-item {{
    display: flex;
    align-items: center;
    gap: 8px;
}}
.report-meta .meta-label {{
    opacity: 0.8;
    font-weight: 500;
}}
.summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 20px;
    margin-bottom: 28px;
}}
.summary-card {{
    background: white;
    padding: 24px;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    border-left: 6px solid #e5e7eb;
    transition: transform 0.2s, box-shadow 0.2s;
}}
.summary-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}}
.summary-card.card-success {{ border-left-color: #10b981; }}
.summary-card.card-failed {{ border-left-color: #ef4444; }}
.summary-card.card-skipped {{ border-left-color: #f59e0b; }}
.summary-card.card-total {{ border-left-color: #3b82f6; }}
.summary-card.card-profile {{ border-left-color: #8b5cf6; }}
.summary-card .card-label {{
    font-size: 13px;
    color: #6b7280;
    font-weight: 500;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.summary-card .card-value {{
    font-size: 36px;
    font-weight: 700;
    color: #111827;
    line-height: 1.1;
}}
.summary-card .card-sub {{
    font-size: 12px;
    color: #9ca3af;
    margin-top: 6px;
}}
.section {{
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    margin-bottom: 28px;
    overflow: hidden;
}}
.section-header {{
    padding: 20px 28px;
    border-bottom: 1px solid #f3f4f6;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}
.section-header h2 {{
    font-size: 18px;
    font-weight: 600;
    color: #111827;
    display: flex;
    align-items: center;
    gap: 10px;
}}
.section-header h2 .icon {{
    width: 32px;
    height: 32px;
    background: #eff6ff;
    color: #2563eb;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
}}
.section-header .badge {{
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}}
.badge-error {{ background: #fee2e2; color: #dc2626; }}
.badge-warn {{ background: #fef3c7; color: #d97706; }}
.badge-ok {{ background: #d1fae5; color: #059669; }}
.badge-info {{ background: #dbeafe; color: #2563eb; }}
.section-body {{
    padding: 24px 28px;
}}
.error-breakdown {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}}
.error-item {{
    background: #fafafa;
    padding: 16px;
    border-radius: 10px;
    border: 1px solid #f0f0f0;
}}
.error-item .error-cat {{
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}
.error-item .error-cat .num {{
    background: #111827;
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 12px;
}}
.error-item.permission {{ border-left: 4px solid #dc2626; }}
.error-item.disk {{ border-left: 4px solid #ea580c; }}
.error-item.inuse {{ border-left: 4px solid #ca8a04; }}
.error-item.notfound {{ border-left: 4px solid #7c3aed; }}
.error-item.io {{ border-left: 4px solid #0891b2; }}
.error-item.other {{ border-left: 4px solid #6b7280; }}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
table th {{
    background: #f9fafb;
    padding: 12px 14px;
    text-align: left;
    font-weight: 600;
    color: #374151;
    border-bottom: 2px solid #e5e7eb;
    white-space: nowrap;
}}
table td {{
    padding: 12px 14px;
    border-bottom: 1px solid #f3f4f6;
    color: #4b5563;
    vertical-align: top;
}}
table tr:hover td {{
    background: #fafbfc;
}}
.path-text {{
    font-family: "Consolas", "Monaco", monospace;
    font-size: 12px;
    color: #1f2937;
    background: #f3f4f6;
    padding: 2px 8px;
    border-radius: 4px;
    word-break: break-all;
}}
.error-text {{
    color: #dc2626;
    font-size: 12px;
    font-family: "Consolas", monospace;
}}
.status-success {{ color: #059669; font-weight: 600; }}
.status-failed {{ color: #dc2626; font-weight: 600; }}
.status-skipped {{ color: #d97706; font-weight: 600; }}
.status-idle {{ color: #6b7280; font-weight: 600; }}
.progress-bar {{
    width: 100%;
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
    margin-top: 6px;
}}
.progress-fill {{
    height: 100%;
    background: linear-gradient(90deg, #10b981, #059669);
    border-radius: 4px;
}}
.progress-fill.has-failed {{
    background: linear-gradient(90deg, #10b981, #ef4444);
}}
.profile-card {{
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin-bottom: 16px;
    overflow: hidden;
}}
.profile-card:last-child {{ margin-bottom: 0; }}
.profile-head {{
    background: #f9fafb;
    padding: 16px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    cursor: pointer;
}}
.profile-head:hover {{ background: #f3f4f6; }}
.profile-title {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 200px;
}}
.profile-name {{
    font-size: 16px;
    font-weight: 600;
    color: #111827;
}}
.profile-paths {{
    font-size: 12px;
    color: #6b7280;
    margin-top: 4px;
}}
.profile-paths span {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-right: 16px;
}}
.profile-stats {{
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}}
.profile-stat {{
    text-align: center;
    min-width: 60px;
}}
.profile-stat .num {{
    font-size: 20px;
    font-weight: 700;
    display: block;
}}
.profile-stat .lbl {{
    font-size: 11px;
    color: #9ca3af;
    text-transform: uppercase;
}}
.profile-detail {{
    padding: 0 20px;
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease;
}}
.profile-detail.open {{
    padding: 16px 20px 20px;
    max-height: 2000px;
}}
.mini-stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
}}
.mini-stat {{
    background: #f9fafb;
    padding: 10px 14px;
    border-radius: 8px;
}}
.mini-stat .lbl {{
    font-size: 11px;
    color: #9ca3af;
}}
.mini-stat .val {{
    font-size: 16px;
    font-weight: 600;
    color: #1f2937;
}}
.time-info {{
    font-size: 12px;
    color: #6b7280;
    margin-bottom: 12px;
}}
.empty-state {{
    text-align: center;
    padding: 40px 20px;
    color: #9ca3af;
    font-size: 14px;
}}
.empty-state .big-icon {{
    font-size: 48px;
    margin-bottom: 12px;
    opacity: 0.5;
}}
.report-footer {{
    text-align: center;
    padding: 24px;
    color: #9ca3af;
    font-size: 12px;
}}
.details-toggle {{
    cursor: pointer;
    user-select: none;
}}
.toggle-icon {{
    display: inline-block;
    transition: transform 0.2s;
    font-size: 12px;
    color: #9ca3af;
}}
.toggle-icon.open {{
    transform: rotate(90deg);
}}
</style>
</head>
<body>
<div class="container">
    <div class="report-header">
        <h1>📊 对账审计报告</h1>
        <div class="subtitle">同步大师 · SyncMaster — 多方案批量同步执行结果审计</div>
        <div class="report-meta">
            <div class="meta-item">
                <span class="meta-label">报告编号：</span>
                <span>{_escape_html(report_id)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">生成时间：</span>
                <span>{_escape_html(generated_at)}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">方案总数：</span>
                <span>{total_profiles} 个</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">最大并发：</span>
                <span>2 个任务</span>
            </div>
        </div>
    </div>

    <div class="summary-grid">
        <div class="summary-card card-total">
            <div class="card-label">总文件数</div>
            <div class="card-value">{total_files}</div>
            <div class="card-sub">{total_profiles} 个同步方案合计</div>
        </div>
        <div class="summary-card card-success">
            <div class="card-label">✅ 成功同步</div>
            <div class="card-value">{total_success}</div>
            <div class="card-sub">文件已正确复制</div>
        </div>
        <div class="summary-card card-failed">
            <div class="card-label">❌ 失败总数</div>
            <div class="card-value">{total_failed}</div>
            <div class="card-sub">影响 {profile_with_issues} 个方案</div>
        </div>
        <div class="summary-card card-skipped">
            <div class="card-label">⏭ 跳过冲突</div>
            <div class="card-value">{total_skipped}</div>
            <div class="card-sub">取消操作或冲突文件</div>
        </div>
        <div class="summary-card card-profile">
            <div class="card-label">📋 方案状态</div>
            <div class="card-value">{successful_profiles}/{total_profiles}</div>
            <div class="card-sub">成功方案 / 全部，{no_diff_profiles} 个无差异</div>
        </div>
    </div>
"""

    if total_failed > 0 or total_skipped > 0:
        html += """
    <div class="section">
        <div class="section-header">
            <h2><span class="icon">⚠️</span>问题分类统计</h2>
            <span class="badge badge-error">存在异常</span>
        </div>
        <div class="section-body">
"""
        if total_failed > 0:
            html += '<div class="error-breakdown">'
            error_icons = {
                "权限不足": ("permission", "🔒"),
                "磁盘空间不足": ("disk", "💾"),
                "文件被占用": ("inuse", "📁"),
                "文件不存在": ("notfound", "❓"),
                "IO错误": ("io", "⚡"),
                "其他错误": ("other", "❔"),
            }
            for cat, count in error_counter.most_common():
                cls_name, icon = error_icons.get(cat, ("other", "❔"))
                html += f"""
                <div class="error-item {cls_name}">
                    <div class="error-cat">
                        <span>{icon} {_escape_html(cat)}</span>
                        <span class="num">{count} 次</span>
                    </div>
                </div>
"""
            html += "</div>"

        if total_failed > 0:
            html += """
            <h3 style="font-size:15px; margin-bottom:12px; color:#374151;">❌ 失败文件明细</h3>
            <table>
                <thead>
                    <tr>
                        <th style="width:120px;">所属方案</th>
                        <th style="width:110px;">错误分类</th>
                        <th>文件相对路径</th>
                        <th>详细错误信息</th>
                    </tr>
                </thead>
                <tbody>
"""
            for r in results:
                for ff in r.failed_files:
                    html += f"""
                    <tr>
                        <td><strong>{_escape_html(r.profile_name)}</strong></td>
                        <td><span class="status-failed">{_escape_html(ff.error_category)}</span></td>
                        <td><span class="path-text">{_escape_html(ff.rel_path)}</span></td>
                        <td><span class="error-text">{_escape_html(ff.error_msg)}</span></td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
"""

        if total_skipped > 0:
            html += f"""
            <h3 style="font-size:15px; margin:24px 0 12px; color:#374151;">⏭ 跳过/冲突文件明细（共 {total_skipped} 项）</h3>
            <table>
                <thead>
                    <tr>
                        <th style="width:120px;">所属方案</th>
                        <th style="width:150px;">跳过原因</th>
                        <th>文件相对路径</th>
                    </tr>
                </thead>
                <tbody>
"""
            for r in results:
                for sf in r.skipped_files:
                    html += f"""
                    <tr>
                        <td><strong>{_escape_html(r.profile_name)}</strong></td>
                        <td><span class="status-skipped">{_escape_html(sf.reason)}</span></td>
                        <td><span class="path-text">{_escape_html(sf.rel_path)}</span></td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
"""
        html += """
        </div>
    </div>
"""

    html += """
    <div class="section">
        <div class="section-header">
            <h2><span class="icon">📁</span>方案执行详情</h2>
            <span class="badge badge-info">点击展开</span>
        </div>
        <div class="section-body">
"""

    for idx, r in enumerate(results):
        pct = 0
        if r.total_files > 0:
            pct = int(r.success_count / r.total_files * 100)
        status_cls = _status_color_class(r)
        status_txt = _status_text(r)
        html += f"""
            <div class="profile-card">
                <div class="profile-head" onclick="toggleDetail('p{idx}')">
                    <div class="profile-title">
                        <span class="toggle-icon" id="icon-p{idx}">▶</span>
                        <div>
                            <div class="profile-name">{_escape_html(r.profile_name)}
                                <span class="{status_cls}">（{_escape_html(status_txt)}）</span>
                            </div>
                            <div class="profile-paths">
                                <span>📤 {_escape_html(r.source_path)}</span>
                                <span>📥 {_escape_html(r.target_path)}</span>
                            </div>
                        </div>
                    </div>
                    <div class="profile-stats">
                        <div class="profile-stat">
                            <span class="num" style="color:#3b82f6;">{r.total_files}</span>
                            <span class="lbl">总计</span>
                        </div>
                        <div class="profile-stat">
                            <span class="num" style="color:#10b981;">{r.success_count}</span>
                            <span class="lbl">成功</span>
                        </div>
                        <div class="profile-stat">
                            <span class="num" style="color:#ef4444;">{r.failed_count}</span>
                            <span class="lbl">失败</span>
                        </div>
                        <div class="profile-stat">
                            <span class="num" style="color:#f59e0b;">{r.skipped_count}</span>
                            <span class="lbl">跳过</span>
                        </div>
                    </div>
                </div>
                <div class="profile-detail" id="detail-p{idx}">
                    <div class="time-info">
                        <strong>开始时间：</strong>{_escape_html(r.started_at) or '—'} &nbsp;&nbsp;|&nbsp;&nbsp;
                        <strong>结束时间：</strong>{_escape_html(r.finished_at) or '—'}
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill{' has-failed' if r.failed_count > 0 else ''}"
                             style="width:{pct}%;"></div>
                    </div>
                    <div style="margin:16px 0;"></div>
                    <div class="mini-stats">
                        <div class="mini-stat">
                            <div class="lbl">扫描总项数</div>
                            <div class="val">{r.scan_total}</div>
                        </div>
                        <div class="mini-stat">
                            <div class="lbl">完全相同</div>
                            <div class="val" style="color:#10b981;">{r.scan_identical}</div>
                        </div>
                        <div class="mini-stat">
                            <div class="lbl">存在差异</div>
                            <div class="val" style="color:#f59e0b;">{r.scan_diff}</div>
                        </div>
                        <div class="mini-stat">
                            <div class="lbl">源路径独有</div>
                            <div class="val" style="color:#3b82f6;">{r.scan_left_only}</div>
                        </div>
                        <div class="mini-stat">
                            <div class="lbl">目标独有</div>
                            <div class="val" style="color:#8b5cf6;">{r.scan_right_only}</div>
                        </div>
                    </div>
"""
        if r.failed_files:
            html += f"""
                    <h4 style="font-size:13px; margin:12px 0 8px; color:#dc2626;">❌ 失败文件（{len(r.failed_files)} 项）</h4>
                    <table>
                        <thead>
                            <tr>
                                <th style="width:140px;">错误分类</th>
                                <th>相对路径</th>
                                <th>错误信息</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for ff in r.failed_files:
                html += f"""
                            <tr>
                                <td><span class="status-failed">{_escape_html(ff.error_category)}</span></td>
                                <td><span class="path-text">{_escape_html(ff.rel_path)}</span></td>
                                <td><span class="error-text">{_escape_html(ff.error_msg)}</span></td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
"""
        if r.skipped_files:
            html += f"""
                    <h4 style="font-size:13px; margin:16px 0 8px; color:#d97706;">⏭ 跳过文件（{len(r.skipped_files)} 项）</h4>
                    <table>
                        <thead>
                            <tr>
                                <th style="width:180px;">原因</th>
                                <th>相对路径</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for sf in r.skipped_files:
                html += f"""
                            <tr>
                                <td><span class="status-skipped">{_escape_html(sf.reason)}</span></td>
                                <td><span class="path-text">{_escape_html(sf.rel_path)}</span></td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
"""
        html += """
                </div>
            </div>
"""

    html += f"""
        </div>
    </div>

    <div class="report-footer">
        本报告由 <strong>同步大师 SyncMaster</strong> 自动生成 · {_escape_html(generated_at)} · 报告编号 {_escape_html(report_id)}
    </div>
</div>

<script>
function toggleDetail(id) {{
    const detail = document.getElementById('detail-' + id);
    const icon = document.getElementById('icon-' + id);
    if (detail.classList.contains('open')) {{
        detail.classList.remove('open');
        icon.classList.remove('open');
    }} else {{
        detail.classList.add('open');
        icon.classList.add('open');
    }}
}}
</script>
</body>
</html>
"""

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html
