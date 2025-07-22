#Arugment parsing
$project_settings_File = $args[0]
$fully_automate = $args[1]

if ([string]::IsNullOrEmpty($project_settings_File))
{
	$project_settings_File = Read-Host -Prompt "Enter absolute path to project settings file"
}

if ([string]::IsNullOrEmpty($fully_automate))
{
	$fully_automate = 0
}

$project_settings_File = $project_settings_File.Trim("""")

#Settings Parsing
$system_settings = "$PSScriptRoot/RealityMeshSystemSettings.txt"

if (!(Test-Path $project_settings_File)) {	
	Write-Output "project settings file does not exist"
	Read-Host -Prompt "Press Enter to exit"
	Return
}

if (!(Test-Path $system_settings))
{
	Write-Output "System settings file does not exist"
	Read-Host -Prompt "Press Enter to exit"
	Return
}

Write-Output "Project and System settings found"

#Project settings
$project_name = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^project_name=" }) -replace "project_name=", ""
$source_Directory_temp = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^source_Directory=" }) -replace "source_Directory=", ""
$source_Directory = $source_Directory_temp.Replace("\", "\\")
$sel_Area_Size = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^sel_Area_Size=" }) -replace "sel_Area_Size=", ""
$offset_coordsys = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_coordsys=" }) -replace "offset_coordsys=", ""
$offset_hdatum = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_hdatum=" }) -replace "offset_hdatum=", ""
$offset_vdatum = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_vdatum=" }) -replace "offset_vdatum=", ""
$offset_x = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_x=" }) -replace "offset_x=", ""
$offset_y = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_y=" }) -replace "offset_y=", ""
$offset_z = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_z=" }) -replace "offset_z=", ""
$orthocam_Resolution = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^orthocam_Resolution=" }) -replace "orthocam_Resolution=", ""
$orthocam_Render_Lowest = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^orthocam_Render_Lowest=" }) -replace "orthocam_Render_Lowest=", ""
$tin_to_dem_Resolution = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^tin_to_dem_Resolution=" }) -replace "tin_to_dem_Resolution=", ""
$tile_scheme = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^tile_scheme=" }) -replace "tile_scheme=", ""
$collision = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^collision=" }) -replace "collision=", ""
$visualLODs = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^visualLODs=" }) -replace "visualLODs=", ""
$project_vdatum = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^project_vdatum=" }) -replace "project_vdatum=", ""
$offset_models = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^offset_models=" }) -replace "offset_models=", ""
$csf_options = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^csf_options=" }) -replace "csf_options=", ""
$faceThresh = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^faceThresh=" }) -replace "faceThresh=", ""
$lodThresh = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^lodThresh=" }) -replace "lodThresh=", ""
$tileSize = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^tileSize=" }) -replace "tileSize=", ""
$srfResolution = (Get-Content "$project_settings_File" | Where-Object { $_ -match "^srfResolution=" }) -replace "srfResolution=", ""

#System settings
$blender_path = (Get-Content "$system_settings" | Where-Object { $_ -match "^blender_path=" }) -replace "blender_path=", ""
if (!(Test-Path $blender_path)) {	
	Write-Output "Blender Path invalid"
	Read-Host -Prompt "Press Enter to exit"
	Return
}
$blender_threads = (Get-Content "$system_settings" | Where-Object { $_ -match "^blender_threads=" }) -replace "blender_threads=", ""
$override_Installation_VBS4 = (Get-Content "$system_settings" | Where-Object { $_ -match "^override_Installation_VBS4=" }) -replace "override_Installation_VBS4=", ""
$override_Path_VBS4 = (Get-Content "$system_settings" | Where-Object { $_ -match "^override_Path_VBS4=" }) -replace "override_Path_VBS4=", ""
if (($override_Installation_VBS4 -eq 1) -and !(Test-Path $override_Path_VBS4)) {	
	Write-Output "VBS4 path invalid"
	Read-Host -Prompt "Press Enter to exit"
	Return
}
$vbs4_version = (Get-Content "$system_settings" | Where-Object { $_ -match "^vbs4_version=" }) -replace "vbs4_version=", ""
$override_Installation_DevSuite = (Get-Content "$system_settings" | Where-Object { $_ -match "^override_Installation_DevSuite=" }) -replace "override_Installation_DevSuite=", ""
$override_Path_DevSuite = (Get-Content "$system_settings" | Where-Object { $_ -match "^override_Path_DevSuite=" }) -replace "override_Path_DevSuite=", ""
$terratools_home_path = (Get-Content "$system_settings" | Where-Object { $_ -match "^terratools_home_path=" }) -replace "terratools_home_path=", ""
$terratools_ssh_path = (Get-Content "$system_settings" | Where-Object { $_ -match "^terratools_ssh_path=" }) -replace "terratools_ssh_path=", ""
if (!(Test-Path $terratools_ssh_path)) {	
	Write-Output "Terratools Path invalid"
	Read-Host -Prompt "Press Enter to exit"
	Return
}


#Running with found settings
$AREYOUSURE = ""
if ($fully_automate -eq 0) 
{
	$AREYOUSURE = Read-Host -Prompt "This script will execute a reality mesh data import process that will produce a new set of terrain inset files ready to use in VBS4. Processing time for the import process will vary with the data being imported. Do you want to proceed (Y/[N])? "
}
else {
	$AREYOUSURE = "y"
}


if ($AREYOUSURE -eq 'y') {
	
	if ($fully_automate -eq 0) 
	{
		if (Test-Path "$PSScriptRoot\Projects\$project_name")
		{
			$newName = Read-Host -Prompt "$project_name already exists in projects folder.  Do you want to rename the project(a)?  Or cancel the process(b)?  (a/b)? "
			if ($newName -eq 'a') {
				$project_name = Read-Host -Prompt "Enter new name for project: "
			}
			else {
				Read-Host -Prompt "Process cancelled.  Press Enter to exit"
				Return
			}
		}
	}
	else {
		if (Test-Path "$PSScriptRoot\Projects\$project_name")
		{
			$timestamp = Get-Date -UFormat "%D_%T" | ForEach-Object { $_ -replace ":", "_" } | ForEach-Object { $_ -replace "/", "-" }
			$tempPath = ($project_name + "_" + $timestamp)
			$project_name = $tempPath
		}
		
		New-Item -Path "$PSScriptRoot\ProjectSettings\GeneratedFiles_DoNotEdit\AutomationHelper.txt" -ItemType "File" -Value "$project_name" -Force
	}
	
	
	$delete = ""
	if ($fully_automate -eq 0) 
	{
		$delete = Read-Host -Prompt "This will delete all temporary data on your devsuite drive for this project name. Do you want to proceed (y/[n])? "
	}
	else {
		$delete = "y"
	}
	
	if ($delete -eq 'y') {
		#Command to clean out &override_Path_DevSuite%):\$project_name and $override_Path_DevSuite:\vbs2\customer\structures\%Name% on each run
		$deletePath = "${override_Path_DevSuite}:\temp\RealityMesh\$project_name\"
		if (Test-Path $deletePath) {
			Write-Output "Deleting $deletePath"
			Remove-Item $deletePath -Force -Recurse
		}
		
		$deletePath2 = "${override_Path_DevSuite}:\vbs2\customer\structures\$project_name\"
		if (Test-Path $deletePath2) {
			Write-Output "Deleting $deletePath2"
			Remove-Item $deletePath2 -Force -Recurse
		}
		
		Write-Output "Cleaned files before creating new ones"
	}	

	#Delete existing settings and create new file
	$generated_settings_file = "$PSScriptRoot\ProjectSettings\GeneratedFiles_DoNotEdit\$project_name.txt"
	if ((Test-Path $generated_settings_file)) {
		Remove-Item -Path $generated_settings_file
	}
	
	$override_Installation_VBS4_bool = "false"
	if ($override_Installation_VBS4 -eq 1) {
		$override_Installation_VBS4_bool = "true"
	}

        $out_in_name = "$project_name"
        $out_in_name_with_drive = ""
        if ($override_Installation_DevSuite -eq 1) {
                $out_in_name_with_drive = "${override_Path_DevSuite}:\temp\RealityMesh\$project_name"
        }
        else {
                $tempDir = Join-Path $env:TEMP 'RealityMesh'
                $out_in_name_with_drive = Join-Path $tempDir $project_name
        }
	
	New-Item -Path $generated_settings_file -ItemType File
	Add-Content -Path $generated_settings_file -Value "set name {$project_name}"
	Add-Content -Path $generated_settings_file -Value "set blender_path {$blender_path}"
	Add-Content -Path $generated_settings_file -Value "set blender_threads {$blender_threads}"
	Add-Content -Path $generated_settings_file -Value "set override_Installation_VBS4_bool {$override_Installation_VBS4_bool}"
	Add-Content -Path $generated_settings_file -Value "set override_Path_VBS4 {$override_Path_VBS4}"
	Add-Content -Path $generated_settings_file -Value "set vbs4_version {$vbs4_version}"
	Add-Content -Path $generated_settings_file -Value "set override_Installation_DevSuite {$override_Installation_DevSuite}"
	Add-Content -Path $generated_settings_file -Value "set override_Path_DevSuite {$override_Path_DevSuite}"
	Add-Content -Path $generated_settings_file -Value "set offset_x {$offset_x}"
	Add-Content -Path $generated_settings_file -Value "set offset_y {$offset_y}"
	Add-Content -Path $generated_settings_file -Value "set offset_z {$offset_z}"
	Add-Content -Path $generated_settings_file -Value "set offset_coordsys {$offset_coordsys}"
	Add-Content -Path $generated_settings_file -Value "set offset_hdatum {$offset_hdatum}"
	Add-Content -Path $generated_settings_file -Value "set offset_vdatum {$offset_vdatum}"
	Add-Content -Path $generated_settings_file -Value "set orthocam_Resolution {$orthocam_Resolution}"
	Add-Content -Path $generated_settings_file -Value "set orthocam_Render_Lowest {$orthocam_Render_Lowest}"
	Add-Content -Path $generated_settings_file -Value "set tin_to_dem_Resolution {$tin_to_dem_Resolution}"
	Add-Content -Path $generated_settings_file -Value "set override_Installation_VBS4 {$override_Installation_VBS4}"
	Add-Content -Path $generated_settings_file -Value "set sel_Area_Size {$sel_Area_Size}"
	Add-Content -Path $generated_settings_file -Value "set out_in_name {$out_in_name}"
	Add-Content -Path $generated_settings_file -Value "set out_in_name_with_drive {$out_in_name_with_drive}"
	Add-Content -Path $generated_settings_file -Value "set collision {$collision}"
	Add-Content -Path $generated_settings_file -Value "set visualLODs {$visualLODs}"
	Add-Content -Path $generated_settings_file -Value "set project_vdatum {$project_vdatum}"
	Add-Content -Path $generated_settings_file -Value "set offset_models {$offset_models}"
	Add-Content -Path $generated_settings_file -Value "set csf_options {$csf_options}"
	Add-Content -Path $generated_settings_file -Value "set faceThresh {$faceThresh}"
	Add-Content -Path $generated_settings_file -Value "set lodThresh {$lodThresh}"
	Add-Content -Path $generated_settings_file -Value "set tileSize {$tileSize}"
	Add-Content -Path $generated_settings_file -Value "set srfResolution {$srfResolution}"
	
	$command_path = "..\..\ProjectSettings\GeneratedFiles_DoNotEdit\$project_name.txt"

	robocopy RealityMesh_tt "Projects\$project_name"
	
	Set-Location -Path "$PSScriptRoot\Projects\$project_name"
	
	Rename-Item -Path "RealityMeshProcess.ttp" -NewName "$project_name.ttp"
	
	"set sourceDir `"$source_Directory`" " | Out-File sourceDir.txt -Encoding Default
	"set tileScheme `"$tile_scheme`" " | Out-File tileScheme.txt -Encoding Default
	if (!([string]::IsNullOrEmpty($terratools_home_path)) -and (Test-Path $terratools_home_path)) {	
		Write-Output "Using custom TERRATOOLS_HOME path at $terratools_home_path"
		$env:TERRASIM_HOME = $terratools_home_path
	}
	$time = Measure-Command {
		#& "$terratools_ssh_path" OneClick.tcl -command_file "$command_path"
		Start-Process -FilePath "$terratools_ssh_path" -Wait -NoNewWindow -ArgumentList "RealityMeshProcess.tcl -command_file `"$command_path`""
	}
	
	$minutes = $time.TotalSeconds / 60 
	Write-Output "`nTime to run TT project: $minutes minutes"
	
	"Time to run TT project: $minutes minutes" | Out-File TimingLog.txt -Encoding Default
} 
else 
{
	Write-Output "You will need to change the project name to avoid overwriting temprory data.  Change the project_name and rerun the ps1"
}

if ($fully_automate -eq 0) 
{
	Read-Host -Prompt "Press Enter to exit"
}
