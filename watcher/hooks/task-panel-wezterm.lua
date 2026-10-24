-- Observe native Codex session identity in each local terminal pane.
local wezterm = require 'wezterm'
local M = {}
local uuid_pattern = '%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x'

local function session_id(pane)
  local title = pane:get_title():lower()
  local identifier = nil
  for candidate in pane:get_lines_as_text():lower():gmatch(uuid_pattern) do
    if title:find(candidate, 1, true) or title:find(candidate:sub(1, 29) .. '...', 1, true) then
      identifier = candidate
    end
  end
  return identifier
end

local function interactive_codex(info)
  if not info or not info.executable or info.executable:match('([^/]+)$') ~= 'codex' then
    return false
  end
  for _, argument in ipairs(info.argv or {}) do
    if argument == 'exec' or argument == 'app-server' or argument == 'mcp-server' then
      return false
    end
  end
  return true
end

local function close_owned(window, record, panes)
  if not record then return end
  local panel = panes[record.panel]
  if panel and panel:get_title():find('cc-hooks-task-panel:', 1, true) == 1 then
    window:perform_action(wezterm.action.CloseCurrentPane { confirm = false }, panel)
  end
end

function M.setup(options)
  wezterm.add_to_config_reload_watch_list(options.hooks .. '/task-panel-wezterm.lua')
  wezterm.on('update-status', function(window, _)
    local key = tostring(window:window_id())
    local all = wezterm.GLOBAL.cc_hooks_task_panels or {}
    local records = all[key] or {}
    local panes = {}
    for _, tab in ipairs(window:mux_window():tabs()) do
      for _, pane in ipairs(tab:panes()) do panes[tostring(pane:pane_id())] = pane end
    end
    for id, record in pairs(records) do
      if not panes[id] then
        close_owned(window, record, panes)
        records[id] = nil
      end
    end
    for id, pane in pairs(panes) do
      local info = pane:get_foreground_process_info()
      if interactive_codex(info) then
        local identifier = session_id(pane)
        if identifier then
          local identity = tostring(info.pid) .. '-' .. identifier
          local previous = records[id]
          if not previous or previous.identity ~= identity then
            close_owned(window, previous, panes)
            local panel = pane:split {
              direction = 'Bottom', size = 3,
              args = { options.python, options.hooks .. '/task_panel_launch.py',
                '--data-dir', options.data_dir, '--session', identifier, '--parent', id,
                '--attachment', identity, '--codex-home', options.codex_home,
                '--title', (info.cwd or ''):match('([^/]+)/*$') or 'Codex' },
            }
            records[id] = { identity = identity, panel = tostring(panel:pane_id()) }
            pane:activate()
          end
        end
      elseif records[id] and info then
        close_owned(window, records[id], panes)
        records[id] = nil
      end
    end
    all[key] = records
    wezterm.GLOBAL.cc_hooks_task_panels = all
  end)
end

return M
