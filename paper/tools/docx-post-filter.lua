--[[ docx-post-filter.lua -- runs after --citeproc.
Lets long URLs in the reference list break after "/", ".", "-" and "_",
like LaTeX's url package, so Word does not stretch justified lines. ]]
function Link(link)
  if not link.target:match("^https?://") then return nil end
  return link:walk({ Str = function(s)
    return pandoc.Str((s.text:gsub("([/%.%-_])", "%1\u{200B}")))
  end })
end
