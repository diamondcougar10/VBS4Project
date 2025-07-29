tav_open world [lindex $argv 0]

world arealapply a {
	a loop 0 l
	if { [l nverts] > 1000 } {
		a del -all *
	}
}

# Save to output file.
world save -remove_unattributed [lindex $argv 1]
