import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../App'

describe('application shell', () => {
  it('renders the Vantage landing page', () => {
    render(<App />)
    expect(screen.getByText('Vantage')).toBeInTheDocument()
  })
})
