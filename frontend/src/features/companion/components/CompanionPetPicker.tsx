import { COMPANION_PETS, type CompanionPetId } from '../lib/sprite'
import { CompanionSprite } from './CompanionSprite'

interface CompanionPetPickerProps {
  selectedPetId: CompanionPetId
  onSelect: (petId: CompanionPetId) => void
}

export function CompanionPetPicker({ selectedPetId, onSelect }: CompanionPetPickerProps) {
  return (
    <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label="桌宠选择">
      {COMPANION_PETS.map((pet) => {
        const selected = pet.id === selectedPetId
        return (
          <button
            key={pet.id}
            type="button"
            aria-label={`选择${pet.displayName}桌宠`}
            aria-pressed={selected}
            title={pet.description}
            onClick={() => onSelect(pet.id)}
            className={`group relative grid min-w-0 place-items-center rounded-[12px] border p-3 text-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg ${
              selected
                ? 'border-fg bg-fg-soft text-fg'
                : 'border-border bg-bg text-muted hover:border-fg hover:text-fg'
            }`}
          >
            <span className="grid h-[74px] w-[74px] place-items-center overflow-hidden rounded-[10px] bg-surface">
              <CompanionSprite
                state="idle"
                cellWidth={68}
                petId={pet.id}
                animated={false}
                label={`${pet.displayName}预览`}
                className="pointer-events-none"
              />
            </span>
            <strong className="mt-2 block w-full truncate text-xs" title={pet.displayName}>
              {pet.displayName}
            </strong>
            <span className="mt-1 block w-full text-[10px] leading-4 text-muted">
              {selected ? '使用中' : '点击选择'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
