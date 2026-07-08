import { useEffect, useState } from 'react'
import { listEnvironments } from '../api'

/** Kända miljönamn för comboboxar (Installationer + Jämför miljöer): både
 * exakta namn ("proj1-backend") och deras projektprefix ("proj1"), eftersom
 * miljöfiltret/diffen matchar hela prefix-gruppen, inte bara exakta namn. */
export function useEnvironmentOptions(): string[] {
  const [options, setOptions] = useState<string[]>([])

  useEffect(() => {
    const controller = new AbortController()
    listEnvironments(controller.signal)
      .then((data) => {
        const names = new Set<string>()
        for (const env of data.items) {
          names.add(env.name)
          const hyphenIndex = env.name.indexOf('-')
          if (hyphenIndex > 0) {
            names.add(env.name.slice(0, hyphenIndex))
          }
        }
        setOptions([...names].sort())
      })
      .catch(() => {
        // förslagslistan är en bekvämlighet, inte kritisk
      })
    return () => controller.abort()
  }, [])

  return options
}
