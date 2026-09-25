import type { ButtonHTMLAttributes } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'dark' | 'onDark'

const variantClasses: Record<ButtonVariant, string> = {
  // Green Accent fill with white text — the main CTA
  primary: 'bg-green-accent text-white border border-green-accent',
  // Green Accent outline on transparent surface
  secondary: 'bg-transparent text-green-accent border border-green-accent',
  // Black filled pill for conversion moments
  dark: 'bg-black text-white border border-black',
  // White outline on dark-green feature bands
  onDark: 'bg-transparent text-white border border-white',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

/**
 * Full-pill button per DESIGN.md: 50px radius on every button without
 * exception, tight tracking, and the signature scale(0.95) active press.
 * On touch surfaces the pill grows to the 44px touch-target floor
 * (DESIGN.md §8) without changing the desktop look.
 */
export function Button({ variant = 'primary', className = '', type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={`pointer-coarse:min-h-11 rounded-pill border px-4 py-[7px] font-semibold tracking-tight transition-all duration-200 ease-in-out active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${className}`}
      {...rest}
    />
  )
}
